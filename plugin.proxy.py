import regex
import sys
import json
import os
import common
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from http.client import HTTPSConnection
from urllib.parse import urlparse, parse_qs
from datetime import datetime
from typing import NamedTuple, List

targetDir = common.to_dir(sys.argv[1])
if targetDir is None:
    sys.exit(f"FATAL! `{arg1}` directory does not exist")
config = common.load_config(targetDir)

chunkSize = config['proxy']['chunk']
charset = config['common']['encoding']
marketplaceHost = config['common']['hosts']['target']
mappings = config['common']['mapping']
connection = HTTPSConnection(marketplaceHost)
locations = common.load_json('Location', targetDir, config['common']['plugins']['location'], charset)
comments = common.load_json('Comments', targetDir, config['common']['plugins']['comments'], charset)

versionMap = {}
replacements = {}

for mapping in mappings:
    if mappings[mapping] is not None:
        re = regex.compile(mapping)
        replacements[re] = mappings[mapping]


class VendorData(NamedTuple):
    name: str
    email: str
    url: str


class IdeaVersionData(NamedTuple):
    min: str
    max: str
    fromBuild: str
    untilBuild: str


class PluginData(NamedTuple):
    code: str
    pluginId: int
    updateId: int
    name: str
    description: str
    version: str
    url: str
    vendor: VendorData
    rating: str
    changeNotes: str
    ideaVersion: IdeaVersionData
    depends: List[str]
    tags: List[str]
    downloads: int
    size: int
    createdDate: datetime
    updatedDate: datetime

    def to_json(self):
        return {
            'id': self.pluginId,
            'name': self.name,
            'xmlId': self.code,
            'paid': False,
            'downloads': self.downloads,
            'rating': self.rating,
            'organization': self.vendor.name,
            'cdate': int(self.createdDate.timestamp() * 1000),
            'updateId': self.updateId,
            'vendorInfo': {
                'name': self.vendor.name,
                'isVerified': self.vendor.name == 'JetBrains s.r.o.'
            }
        }


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = config['proxy']['version']

    def log_request(self, code):
        pass

    def load(self, conn):
        headers = {}
        for h, v in self.headers.items():
            if h.lower() == 'host':
                headers[h] = marketplaceHost
            else:
                headers[h] = v
        conn.request("GET", self.path, headers=headers, encode_chunked=True)
        response = conn.getresponse()
        self.send_response(response.status)
        for header, value in response.getheaders():
            if header.lower() == 'location':
                print('UNKN', 'Location', ':', value)
            self.send_header(header, value)
        self.end_headers()

        if not response.chunked:
            print('UNKN', 'Not chunked')
            while chunk := response.read(chunkSize):
                self.wfile.write(chunk)
        else:
            print('UNKN', 'Chunked')
            while not response.isclosed():
                if chunk := response.read(chunkSize):
                    self.wfile.write('{:x}\r\n'.format(len(chunk)).encode(charset))
                    self.wfile.write(chunk)
                    self.wfile.write('\r\n'.encode(charset))
                    self.wfile.flush()
                else:
                    break
            self.wfile.write('0\r\n\r\n'.encode(charset))

        print('UNKN', 'Done')

    def forward(self, prefix, path):
        location = f"https://{marketplaceHost}{path}"

        self.send_response(301)
        self.send_header('Location', location)
        self.end_headers()

        print(prefix, 'Forward to', location)

    def do_GET(self):
        for pattern in replacements:
            match = pattern.fullmatch(self.path)
            if match is not None:
                result = replacements[pattern]
                if result is None:
                    self.send_error(404)
                else:
                    self.forward('AUTO', pattern.sub(result, self.path))
                return

        if self.path.startswith('/pluginManager'):
            print('PLGN', 'Requesting', self.path)
            url = urlparse(self.path)
            inParams = parse_qs(url.query)

            inIds = inParams.get('id', [''])
            inBuild = inParams.get('build', [''])[0]

            items = lookup(inBuild, inIds)
            id = str(items[0].get('id'))

            self.forward('PLGN', locations[id])
        elif self.path.startswith('/api/search/plugins'):
            print('SRCH', 'Searching', self.path)
            url = urlparse(self.path)
            params = parse_qs(url.query)

            paramBuild = params.get('build', [''])[0]
            paramSearch = params.get('search', [''])[0]
            paramMax = int(params.get('max', ['0'])[0])

            if paramSearch == '':
                results = random(paramBuild, paramMax)
            else:
                results = search(paramBuild, paramSearch)

            content = json.dumps(results).encode(charset)

            self.send_response(200)
            self.send_header('Content-Type', f"application/json; charset={charset}")
            self.send_header('Content-Length', len(content))
            self.end_headers()
            self.wfile.write(content)

            print('SRCH', f"Found {len(results)} plugins")
        elif self.path.startswith('/api/search/updates/compatible'):
            print('UPDT', 'Searching', self.path)
            url = urlparse(self.path)
            params = parse_qs(url.query)

            paramBuild = params.get('build', [''])[0]
            paramXmlIds = params.get('pluginXmlId', [''])

            if paramXmlIds == ['']:
                self.send_response(204)
                self.end_headers()

                print('UPDT', 'No content')
            else:
                items = lookup(paramBuild, paramXmlIds)

                content = json.dumps(items).encode(charset)

                self.send_response(200)
                self.send_header('Content-Type', f"application/json; charset={charset}")
                self.send_header('Content-Length', len(content))
                self.end_headers()
                self.wfile.write(content)

                if len(items) == 0:
                    print('UPDT', 'Not found...')
                else:
                    print('UPDT', f"Found {len(items)} plugin updates")
        elif self.path.startswith('/api/icon'):
            url = urlparse(self.path)
            params = parse_qs(url.query)

            id = params.get('pluginId', ['..'])[0].replace(' ', '_').lower()
            icon = params.get('theme', ['DEFAULT'])[0].lower()

            self.forward('ICON', f"/files/icons/intellij/{id}/{icon}.svg")
        elif self.path.startswith('/api/products/intellij/plugins/') and self.path.endswith('/comments'):
            name = self.path.removeprefix('/api/products/intellij/plugins/').removesuffix('/comments')

            if name in comments:
                result = comments[name]
            else:
                result = []

            content = json.dumps(result).encode(charset)
            self.send_response(200)
            self.send_header('Content-Type', f"application/json; charset={charset}")
            self.send_header('Content-Length', len(content))
            self.end_headers()
            self.wfile.write(content)
            print('CMNT', len(result), 'comments')
        elif self.path.startswith('/feature/getImplementations?featureType='):
            print('IMPL', 'Fetching', self.path)
            url = urlparse(self.path)
            params = parse_qs(url.query)

            feature_type = params.get('featureType', [''])[0]

            if feature_type in config['common']['featureTypes']:
                ft = config['common']['featureTypes'][featureType]

                impl_file = common.to_path(targetDir, f"impl.{ft}.json")

                self.send_response(200)
                self.send_header('Content-Type', f"application/json; charset={charset}")
                self.send_header('Content-Type', impl_file.stat().st_size)
                self.end_headers()
                with impl_file.open(mode='rb') as f:
                    self.wfile.write(f.read())

                print('IMPL', 'Fetched', impl_file)
            else:
                self.send_error(404)
                print('IMPL', 'Not found', self.path)
        else:
            print('UKWN', self.path)
            self.load(connection)


def init(version):
    result = {}
    dict = {}

    for item in common.load_json(f"Plugins {version}", targetDir, f"plugins.{version}.json", charset):
        dict[item['pluginXmlId']] = item

    tree = common.load_xml(f"Plugins {version}", targetDir, f"plugins.{version}.xml", charset)
    root = tree.getroot()
    categories = root.findall('category')

    for category in categories:
        for plugin in category.findall('idea-plugin'):
            xmlDownloads = plugin.get('downloads')
            xmlSize = plugin.get('size')
            xmlDate = plugin.get('date')
            xmlUpdatedDate = plugin.get('updatedDate')
            xmlUrl = plugin.get('url')
            xmlId = plugin.find('id').text
            xmlName = plugin.find('name').text
            xmlDescription = plugin.find('description').text
            xmlVersion = plugin.find('version').text
            xmlVendor = plugin.find('vendor')
            xmlVendorName = xmlVendor.text
            xmlVendorEmail = xmlVendor.get('email')
            xmlVendorUrl = xmlVendor.get('url')
            xmlRating = plugin.find('rating').text
            xmlChangeNotes = plugin.find('change-notes').text
            xmlIdeaVersion = plugin.find('idea-version')
            xmlIdeaVersionMin = xmlIdeaVersion.get('min')
            xmlIdeaVersionMax = xmlIdeaVersion.get('max')
            xmlIdeaVersionFrom = xmlIdeaVersion.get('since-build')
            xmlIdeaVersionUntil = xmlIdeaVersion.get('until-build')
            xmlDepends = list(map(lambda x: x.text, plugin.findall('depends')))
            xmlTags = list(map(lambda x: x.text, plugin.findall('tags')))
            jsonPluginId = dict[xmlId]['pluginId']
            jsonUpdateId = dict[xmlId]['id']
            jsonVersion = dict[xmlId]['version']

            if xmlVersion != jsonVersion:
                print(f"Inconsistent versioning for `{xmlId}`. XML has `{xmlVersion}` and JSON has `{jsonVersion}`")

            result[xmlId] = PluginData(
                xmlId, int(jsonPluginId), int(jsonUpdateId), xmlName, xmlDescription, jsonVersion, xmlUrl,
                VendorData(xmlVendorName, xmlVendorEmail, xmlVendorUrl),
                xmlRating, xmlChangeNotes,
                IdeaVersionData(xmlIdeaVersionMin, xmlIdeaVersionMax, xmlIdeaVersionFrom, xmlIdeaVersionUntil),
                xmlDepends, xmlTags, xmlDownloads, xmlSize,
                datetime.fromtimestamp(int(xmlDate) / 1e3), datetime.fromtimestamp(int(xmlUpdatedDate) / 1e3)
            )

    return result


def safe_plugins(version):
    if version not in versionMap:
        plugins = init(version)
        versionMap[version] = plugins
    else:
        plugins = versionMap[version]

    return plugins


def lookup(version, plugin_ids):
    plugins = safe_plugins(version)
    results = []

    for id in plugin_ids:
        result = plugins.get(id)
        if result is not None:
            results.append({
                'id': result.updateId,
                'pluginId': result.pluginId,
                'version': result.version,
                'pluginXmlId': result.code
            })

    return results


def random(version, cnt):
    plugins = safe_plugins(version)
    result = []

    for key, value in plugins.items():
        if (cnt > 0):
            result.append(value.to_json())
            cnt -= 1
        else:
            break

    return result


def search(version, term):
    plugins = safe_plugins(version)
    result = []
    lt = term.lower()

    for key, value in plugins.items():
        if key.lower().find(lt) >= 0 or value.name.lower().find(lt) >= 0 or value.description.lower().find(lt) >= 0:
            result.append(value.to_json())

    return result


host = config['proxy']['host']
port = config['proxy']['port']
webServer = HTTPServer((host, port), ProxyHandler)
print(f"Server has started at http://{host}:{port}")

try:
    webServer.serve_forever()
except KeyboardInterrupt:
    print("Terminating...")

webServer.server_close()
print("Server stopped...")
connection.close()
print("Client stopped...")
