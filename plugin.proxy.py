import sys
import json
import os
import xml.etree.ElementTree as ET
from http.server import HTTPServer, BaseHTTPRequestHandler
from http.client import HTTPSConnection
from urllib.parse import urlparse, parse_qs
from datetime import datetime
from typing import NamedTuple, List

hostName = 'localhost'
serverPort = 8000
targetDir = sys.argv[1]
chunkSize = 4096
charset = 'utf-8'
marketplaceHost = 'downloads.marketplace.jetbrains.com'
pluginsHost = 'plugins.jetbrains.com'
connection = HTTPSConnection(marketplaceHost)
temp = HTTPSConnection(pluginsHost)
versionMap = {}
locations = {}

try:
    with open(f"{targetDir}\\plugins.location.json", 'r') as f:
        locations = json.load(f)

    print(f"Loaded {len(locations)} existing plugin locations")
except FileNotFoundError:
    print(f"No file with plugin locations: {locationFile}")
    locations = {}


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
    protocol_version = 'HTTP/1.1'

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
            if (header.lower() == 'location'):
                print('Location', ':', value)
            self.send_header(header, value)
        self.end_headers()

        if not response.chunked:
            print('Not chunked')
            while chunk := response.read(chunkSize):
                self.wfile.write(chunk)
        else:
            print('Chunked')
            while not response.isclosed():
                if chunk := response.read(chunkSize):
                    self.wfile.write('{:x}\r\n'.format(len(chunk)).encode(charset))
                    self.wfile.write(chunk)
                    self.wfile.write('\r\n'.encode(charset))
                    self.wfile.flush()
                else:
                    break
            self.wfile.write('0\r\n\r\n'.encode(charset))

    def do_GET(self):
        if self.path == '/geo/files/prices':
            redirect = f"https://{marketplaceHost}/files/prices/pl"

            self.send_response(301)
            self.send_header('Location', redirect)
            self.end_headers()
            print('FILE', redirect)
        elif self.path == '/favicon.ico':
            self.send_error(404)
        elif self.path.startswith('/.well-known'):
            self.send_error(404)
        elif self.path.startswith('/files/'):
            print('\rFILE', self.path, end='', flush=True)
            redirect = f"https://{marketplaceHost}{self.path}"

            self.send_response(301)
            self.send_header('Location', redirect)
            self.end_headers()
            print('\rFILE', redirect)
        elif self.path.startswith('/pluginManager'):
            url = urlparse(self.path)
            inParams = parse_qs(url.query)

            inId = inParams.get('id', [''])[0]
            inBuild = inParams.get('build', [''])[0]

            item = lookup(inBuild, inId)
            id = str(item.updateId)

            redirect = f"https://{marketplaceHost}{locations[id]}"

            self.send_response(301)
            self.send_header('Location', redirect)
            self.end_headers()

            print('PLGN', redirect)
        elif self.path.startswith('/api/search/plugins'):
            url = urlparse(self.path)
            params = parse_qs(url.query)

            paramBuild = params.get('build', [''])[0]
            paramSearch = params.get('search', [''])[0]
            paramMax = int(params.get('max', ['0'])[0])

            if (paramSearch == ''):
                content = json.dumps(random(paramBuild, paramMax)).encode(charset)
            else:
                content = json.dumps(search(paramBuild, paramSearch)).encode(charset)

            self.send_response(200)
            self.send_header('Content-Type', f"application/json; charset={charset}")
            self.send_header('Content-Length', len(content))
            self.end_headers()
            self.wfile.write(content)
        elif self.path.startswith('/api/search/updates/compatible'):
            print('\rUPDT', 'Searching', end='', flush=True)
            url = urlparse(self.path)
            params = parse_qs(url.query)

            paramBuild = params.get('build', [''])[0]
            paramXmlId = params.get('pluginXmlId', [''])[0]

            item = lookup(paramBuild, paramXmlId)

            if item is None:
                content = ('[{"id":0,"pluginId":0,"version":0,"pluginXmlId":"' + paramXmlId + '"}]').encode(charset)
            else:
                content = json.dumps([{
                    'id': item.updateId,
                    'pluginId': item.pluginId,
                    'version': item.version,
                    'pluginXmlId': item.code
                }]).encode(charset)

            self.send_response(200)
            self.send_header('Content-Type', f"application/json; charset={charset}")
            self.send_header('Content-Length', len(content))
            self.end_headers()
            self.wfile.write(content)
            print('\rUPDT', f"Found {item.code}:{item.version}")
        elif self.path.startswith('/api/icon'):
            url = urlparse(self.path)
            params = parse_qs(url.query)

            id = params.get('pluginId', ['..'])[0].replace(' ', '_').lower()
            icon = params.get('theme', ['DEFAULT'])[0].lower()

            redirect = f"https://{marketplaceHost}/files/icons/intellij/{id}/{icon}.svg"

            self.send_response(301)
            self.send_header('Location', redirect)
            self.end_headers()

            print('ICON', redirect)
        elif self.path.startswith('/api/products/intellij/plugins/') and self.path.endswith('/comments'):
            name = self.path.removeprefix('/api/products/intellij/plugins/').removesuffix('/comments')
            content = json.dumps([{
                'id': 3158,
                'cdate': '1233959549000',
                'comment': 'temporary',
                'rating': 5,
                'plugin': {
                    'id': 2,
                    'name': name,
                    'link': '/plugin/link'
                },
                'author': {
                    'id': '275364ce-247e-420d-ab88-a4521ff20e8f',
                    'name': 'Stas Davydov',
                    'link': '/author/275364ce-247e-420d-ab88-a4521ff20e8f'
                }
            }]).encode(charset)

            self.send_response(200)
            self.send_header('Content-Type', f"application/json; charset={charset}")
            self.send_header('Content-Length', len(content))
            self.end_headers()
            self.wfile.write(content)
        elif self.path.startswith('/feature/getImplementations?featureType='):
            url = urlparse(self.path)
            params = parse_qs(url.query)

            featureType = params.get('featureType', [''])[0]

            impl_file = f"{targetDir}\\impl.{featureType}.json"

            self.send_response(200)
            self.send_header('Content-Type', f"application/json; charset={charset}")
            self.send_header('Content-Type', os.path.getsize(impl_file))
            self.end_headers()
            with open(impl_file, 'rb') as f:
                self.wfile.write(f.read())

            print('IMPL', impl_file)
        else:
            print('UKWN', self.path)
            headers = {}
            for h, v in self.headers.items():
                if h.lower() == 'host':
                    headers[h] = pluginsHost
                else:
                    headers[h] = v
            temp.request("GET", self.path, headers=headers, encode_chunked=True)
            response = temp.getresponse()
            chunked = response.chunked
            self.send_response(response.status)
            for header, value in response.getheaders():
                if (header.lower() == 'location'):
                    print('Location', ':', value)
                self.send_header(header, value)
            self.end_headers()

            if not chunked:
                print('Not chunked')
                while chunk := response.read(chunkSize):
                    self.wfile.write(chunk)
            else:
                print('Chunked')
                while not response.isclosed():
                    if chunk := response.read(chunkSize):
                        self.wfile.write('{:x}\r\n'.format(len(chunk)).encode(charset))
                        self.wfile.write(chunk)
                        self.wfile.write('\r\n'.encode(charset))
                        self.wfile.flush()
                    else:
                        break
                self.wfile.write('0\r\n\r\n'.encode(charset))


def init(version):
    result = {}
    dict = {}

    with open(f"{targetDir}\\plugins.{version}.json", 'r') as f:
        for item in json.load(f):
            dict[item['pluginXmlId']] = item

    tree = ET.parse(f"{targetDir}\\plugins.{version}.xml")
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


def lookup(version, pluginXmlId):
    plugins = safe_plugins(version)
    return plugins.get(pluginXmlId)


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


webServer = HTTPServer((hostName, serverPort), ProxyHandler)
print(f"Server has started at http://{hostName}:{serverPort}")

try:
    webServer.serve_forever()
except KeyboardInterrupt:
    print("Terminating...")

webServer.server_close()
print("Server stopped...")
connection.close()
temp.close()
print("Client stopped...")
