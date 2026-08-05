import sys
import platform

print("OS Name:", platform.system())   # e.g., 'Windows', 'Linux', 'Darwin' (macOS)
print("Release:", platform.release())  # e.g., '10', '5.15.0-72-generic', '23.5.0'
print("Version:", platform.version())  # e.g., Complete detailed build/compilation string

def linux_distribution():
    try:
        return platform.linux_distribution()
    except:
        return "N/A"

def dist():
    try:
        return platform.dist()
    except:
        return "N/A"

print("""Python version: %s
dist: %s
linux_distribution: %s
system: %s
machine: %s
platform: %s
uname: %s
version: %s
mac_ver: %s
""" % (
    sys.version.split('\n'),
    str(dist()),
    linux_distribution(),
    platform.system(),
    platform.machine(),
    platform.platform(),
    platform.uname(),
    platform.version(),
    platform.mac_ver(),
))