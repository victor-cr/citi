import json
import yaml
import xml.etree.ElementTree as ET
from pathlib import Path, PurePath


def to_dir(directory: str):
    dir = Path(directory)
    if dir.is_dir():
        return dir.resolve()
    else:
        return None


def to_path(directory: Path, name: str):
    return directory /name


def load_config(directory: Path):
    name = 'config.yaml'
    config = {}
    file = to_path(directory, name)
    if file.exists() and file.is_file():
        try:
            size = file.stat().st_size
            with file.open(mode='r') as f:
                config = yaml.safe_load(f)
            print(f"Configuration YAML loaded: {file} [{len(config)}/{size}]")
        except yaml.YAMLError:
            print(f"Configuration YAML is corrupted: {file}")
    else:
        print(f"Configuration YAML not found: {directory}/{name}")
    return config


def load_json(description: str, directory: Path, name: str, encoding: str):
    result = {}
    file = to_path(directory, name)
    if file.exists() and file.is_file():
        try:
            size = file.stat().st_size
            with file.open(mode='r', encoding=encoding) as f:
                result = json.load(f)
            print(f"{description} JSON loaded: {file} [{len(result)}/{size}]")
        except json.JSONDecodeError:
            print(f"{description} JSON is corrupted: {file}")
    else:
        print(f"{description} JSON not found: {directory}/{name}")
    return result


def load_xml(description: str, directory: Path, name: str, encoding: str):
    file = to_path(directory, name)
    if file.exists() and file.is_file():
        try:
            size = file.stat().st_size
            result = ET.parse(str(file.resolve()))
            print(f"{description} XML loaded: {file} [{size}]")
            return result
        except ET.ParseError:
            print(f"{description} XML is corrupted: {file}")
    else:
        print(f"{description} XML not found: {directory}/{name}")
    return None


def write_file(description: str, directory: Path, name: str, content: bytes):
    file = to_path(directory, name)
    try:
        with file.open(mode='wb') as f:
            f.write(content)
        print(f"{description} content has written: {file} [{len(content)}]")
    except PermissionError:
        print(f"Error: You do not have permission to write: {file}")
    except IsADirectoryError:
        print(f"Error: `{file}` is a directory, not a file.")
    except OSError as e:
        print(f"Error: System error during writing a file: {file}. An error occurred: {e}")


def write_json(description: str, directory: Path, name: str, content, encoding: str, sort_keys: bool = True):
    file = to_path(directory, name)
    try:
        with file.open(mode='w', encoding=encoding) as f:
            json.dump(content, f, indent='\t', sort_keys=sort_keys)
        print(f"{description} JSON content has written: {file} [{len(content)}/{file.stat().st_size}]")
    except PermissionError:
        print(f"Error: You do not have permission to write: {file}")
    except IsADirectoryError:
        print(f"Error: `{file}` is a directory, not a file.")
    except OSError as e:
        print(f"Error: System error during writing a file: {file}. An error occurred: {e}")
