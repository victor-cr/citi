import requests
import json
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.parse import urlencode

targetDir = sys.argv[1]
baseUrl = 'https://plugins.jetbrains.com'
osystem = 'Windows 11.0'
arch = 'X86_64'
versions = ['IU-261.22158.277', 'IU-261.24374.151', 'IU-261.26222.65', 'IU-262.8665.337']
bucketSize = 40
startedAt = datetime.now()
locationFile = f"{targetDir}\\plugins.location.json"

print("Started at", startedAt)

with requests.Session() as session:
    featureTypes = ['dependencySupport', 'com.intellij.fileTypeFactory']

    for ft in featureTypes:
        response = session.get(f"{baseUrl}/feature/getImplementations?featureType={ft}")

        if response.status_code == 200:
            with open(f"{targetDir}\\impl.{ft}.json", 'w') as f:
                json.dump(
                    sorted(response.json(), key=lambda x: x["pluginId"]),
                    f,
                    indent='\t',
                    sort_keys=True
                )

            print(f"Loaded `{ft}` implementations: {len(response.content)} bytes")
        else:
            print(f"Error getting `{ft}` implementations: {response.status_code}")

    locations = {}

    try:
        with open(locationFile, 'r') as f:
            locations = json.load(f)

        size = os.path.getsize(locationFile)

        print(f"Loaded {len(locations)} existing plugin locations: {size} bytes")
    except FileNotFoundError:
        print(f"No file with plugin locations: {locationFile}")
        locations = {}

    for version in versions:
        response = session.get(f"{baseUrl}/plugins/list/?build={version}")

        if response.status_code == 200:
            xmlFile = f"{targetDir}\\plugins.{version}.xml"
            with open(xmlFile, 'wb') as f:
                f.write(response.content)

            print(f"Loaded `{version}` plugins XML: {len(response.content)} bytes")

            tree = ET.parse(xmlFile)
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
                        'arch': arch,
                        'build': version,
                        'os': osystem,
                        'pluginXmlId': bucket
                    }

                    request = f"{baseUrl}/api/search/updates/compatible?{urlencode(params, True)}"

                    jsonResponse = session.get(request)

                    if jsonResponse.status_code == 200:
                        data = jsonResponse.json()

                        for v in data:
                            id = str(v['id'])
                            if id not in locations:
                                locations[id] = None

                        plugins += data
                        i += len(bucket)
                        b += len(jsonResponse.content)
                    else:
                        print(f"Error `{categoryName}` plugin JSON: {jsonResponse.status_code}")

                iCategories += 1
                delta = datetime.now() - parsedAt
                print(f"Loaded {iCategories}/{lenCategories} `{categoryName}` [{lenList}] in {delta.total_seconds()} sec: {b} bytes")

            pluginFile = f"{targetDir}\\plugins.{version}.json"
            with open(pluginFile, 'w') as f:
                json.dump(
                    sorted(plugins, key=lambda x: x["pluginId"]),
                    f,
                    indent='\t',
                    sort_keys=True
                )

            print(f"Loaded `{version}` [{len(plugins)}] plugins: {os.path.getsize(pluginFile)} bytes")
        else:
            print(f"Error `{version}` plugin XML: {response.status_code}")

    locationAt = datetime.now()

    for k in locations:
        if locations[k] is None:
            r = session.head(f"{baseUrl}/plugin/download?rel=true&updateId={k}")
            locations[k] = r.headers.get('Location')
            print(f"Loaded new location #{k}: {locations[k]}")

    delta = datetime.now() - locationAt
    print(f"Loaded {len(locations)} locations in {delta.total_seconds()} sec")

    with open(locationFile, 'w') as f:
        json.dump(
            dict(
                sorted(
                    locations.items(),
                    key=lambda item: int(item[0])
                )
            ),
            f,
            indent='\t'
        )

    completedAt = datetime.now()
    delta = completedAt - startedAt
    print(f"Completed execution in {delta.total_seconds()} sec")