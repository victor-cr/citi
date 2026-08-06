import requests
import regex
import yaml
import json
import os
import sys
import common
from datetime import datetime
from urllib.parse import quote, urlencode

##
##
##

arg2 = None

targetDir = common.to_dir(sys.argv[1])

if targetDir is None:
    sys.exit(f"FATAL! `{sys.argv[1]}` directory does not exist")

if len(sys.argv) > 2:
    arg2 = sys.argv[2]

config = common.load_config(targetDir)
sourceUrl = f"https://{config['common']['hosts']['source']}"
targetUrl = f"https://{config['common']['hosts']['target']}"
bucketSize = int(config['loader']['bucket'])
charset = config['common']['encoding']
mappings = config['common']['mapping']
locationFile = targetDir / config['common']['plugins']['location']
startedAt = datetime.now()

print("Started at", startedAt)

replacements = {}
reSourceUrl = sourceUrl.replace('.', '\\.')

for mapping in mappings:
    if mappings[mapping] is not None:
        pattern = mapping

        if pattern.startswith('^'):
            pattern = '"' + reSourceUrl + pattern[1:]
        else:
            pattern = '"' + reSourceUrl + pattern

        if pattern.endswith('$'):
            pattern = pattern[:len(pattern)-1] + '"'
        else:
            pattern = pattern + '"'

        re = regex.compile(pattern)
        replacements[re] = '"' + targetUrl + mappings[mapping] + '"'

with requests.Session() as session:
    session.headers.update({
        'Accept-Encoding': config['common']['http']['acceptEncoding'],
        'User-Agent': config['common']['http']['userAgent']
    })

    for ft in config['common']['featureTypes']:
        response = session.get(f"{sourceUrl}/feature/getImplementations?featureType={ft}")

        if response.status_code == 200:
            common.write_json(
                f"Implementation {ft}",
                targetDir,
                config['common']['featureTypes'][ft],
                sorted(response.json(), key=lambda x: x["pluginId"]),
                encoding=charset
            )
        else:
            print(f"Error getting `{ft}` implementations: {response.status_code}")

    comments = common.load_json(
        'Comment plugins',
        targetDir,
        config['common']['plugins']['comments'],
        encoding=charset
    )
    locations = common.load_json(
        'Location plugins',
        targetDir,
        config['common']['plugins']['location'],
        encoding=charset
    )

    for appConfig in config['common']['applications']:
        for info in appConfig['builds']:
            if info.get('enabled', False):
                appBuild = appConfig['code'] + '-' + info['build']
                appName = appConfig['name'] + ' ' + info['version']
                response = session.get(f"{sourceUrl}/plugins/list/?build={appBuild}")

                if response.status_code == 200:
                    xmlFile = f"plugins.{appBuild}.xml"
                    xmlContent = response.text

                    for re in replacements:
                        xmlContent = re.sub(replacements[re], xmlContent)

                    common.write_file(
                        f"{appName} plugin XML",
                        targetDir,
                        xmlFile,
                        xmlContent.encode(charset)
                    )
                    tree = common.load_xml(
                        f"{appName} plugin",
                        targetDir,
                        xmlFile,
                        encoding=charset
                    )

                    root = tree.getroot()
                    categories = root.findall('category')
                    lenCategories = len(categories)
                    iCategories = 0
                    plugins = []

                    for category in categories:
                        parsedAt = datetime.now()
                        categoryName = category.get('name')
                        idList = []

                        for plugin in category.findall('idea-plugin'):
                            idList.append(plugin.find('id').text)

                        lenList = len(idList)
                        i = 0
                        b = 0
                        buckets = [idList[i:i + bucketSize] for i in range(0, lenList, bucketSize)]

                        for bucket in buckets:
                            params = {
                                'arch': config['common']['arch'],
                                'build': appBuild,
                                'os': config['common']['os'],
                                'pluginXmlId': bucket
                            }

                            request = f"{sourceUrl}/api/search/updates/compatible?{urlencode(params, True)}"

                            jsonResponse = session.get(request)

                            if jsonResponse.status_code == 200:
                                data = jsonResponse.json()

                                for v in data:
                                    id = str(v['id'])
                                    code = v['pluginXmlId']
                                    if code not in comments:
                                        comments[code] = None
                                    if id not in locations:
                                        locations[id] = None

                                plugins += data
                                i += len(bucket)
                                b += len(jsonResponse.content)
                            else:
                                print(f"Error `{categoryName}` plugin JSON: {jsonResponse.status_code}")

                        iCategories += 1
                        delta = datetime.now() - parsedAt
                        deltaSec = delta.total_seconds()
                        print(
                            f"Loaded {iCategories}/{lenCategories} `{categoryName}` [{lenList}] in {deltaSec} sec: {b} bytes")

                    common.write_json(
                        f"{appName} plugin",
                        targetDir,
                        f"plugins.{appBuild}.json",
                        sorted(plugins, key=lambda x: x["pluginId"]),
                        encoding=charset
                    )
                else:
                    print(f"Error `{appName}` plugin XML: {response.status_code}")

    commentsAt = datetime.now()
    i = 0
    commentsLen = len(comments)

    for k in comments:
        i += 1
        if arg2 is not None or comments[k] is None:
            r = session.get(f"{sourceUrl}/api/products/intellij/plugins/{quote(k, safe='')}/comments")
            if jsonResponse.status_code == 200:
                try:
                    comment = r.json()
                    print(f"Loaded comments [{i}/{commentsLen}]: {k} [{len(comment)}]")
                    comments[k] = comment
                except requests.exceptions.JSONDecodeError as e:
                    print('Error', k, '`', r.content.decode(charset), '`:', e)
                    comments[k] = []
                except json.decoder.JSONDecodeError as e:
                    print('Error', k, '`', r.content.decode(charset), '`:', e)
                    comments[k] = []
            else:
                print(f"Failed loading comments: {k}")
                comments[k] = []

    delta = datetime.now() - commentsAt
    print(f"Loaded {len(comments)} comments in {delta.total_seconds()} sec")

    common.write_json(
        f"Comments",
        targetDir,
        config['common']['plugins']['comments'],
        comments,
        encoding=charset
    )

    locationAt = datetime.now()

    for k in locations:
        if locations[k] is None:
            r = session.head(f"{sourceUrl}/plugin/download?rel=true&updateId={k}")
            locations[k] = r.headers.get('Location')
            print(f"Loaded new location #{k}: {locations[k]}")

    delta = datetime.now() - locationAt
    print(f"Loaded {len(locations)} locations in {delta.total_seconds()} sec")

    common.write_json(
        f"Locations",
        targetDir,
        config['common']['plugins']['location'],
        dict(sorted(locations.items(), key=lambda item: int(item[0]))),
        encoding=charset,
        sort_keys=False
    )

    completedAt = datetime.now()
    delta = completedAt - startedAt
    print(f"Completed execution in {delta.total_seconds()} sec")
