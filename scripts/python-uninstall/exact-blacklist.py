#!/usr/bin/env python3

import os
import argparse
import sqlite3
import subprocess
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

def fetch_blacklist_url(url):

    if not url:
        return

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:103.0) Gecko/20100101 Firefox/103.0'}

    try:
        response = urlopen(Request(url, headers=headers))
    except HTTPError as e:
        print('[X] HTTP Error:', e.code, 'whilst fetching', url)
        print('\n')
        exit(1)
    except URLError as e:
        print('[X] URL Error:', e.reason, 'whilst fetching', url)
        print('\n')
        exit(1)

    # Read and decode
    response = response.read().decode('UTF-8').replace('\r\n', '\n')

    # If there is data
    if response:
        # Strip leading and trailing blackspace
        response = '\n'.join(x.strip() for x in response.splitlines())

    # Return the hosts
    return response


def dir_path(string):
    if os.path.isdir(string):
        return string
    else:
        raise NotADirectoryError(string)


def restart_pihole(docker):
    if docker is True:
        subprocess.call("docker exec -it pihole pihole restartdns reload",
                        shell=True, stdout=subprocess.DEVNULL)
    else:
        subprocess.call(['pihole', 'restartdns', 'reload'],
                        stdout=subprocess.DEVNULL)


parser = argparse.ArgumentParser()
parser.add_argument("-d", "--dir", type=dir_path,
                    help="Optional: Pi-hole /etc directory")
parser.add_argument(
    "-D", "--docker",  action='store_true', help="Optional: Set if you're using Pi-hole in a Docker environment")
args = parser.parse_args()

if args.dir:
    pihole_location = args.dir
else:
    pihole_location = r'/etc/pihole'

blacklist_remote_url = 'https://raw.githubusercontent.com/slyfox1186/pihole-regex/main/domains/blacklist/exact-blacklist.txt'
remote_sql_url = 'https://raw.githubusercontent.com/slyfox1186/pihole-regex/main/domains/blacklist/exact-blacklist.sql'
gravity_blacklist_location = os.path.join(pihole_location, 'blacklist.txt')
gravity_db_location = os.path.join(pihole_location, 'gravity.db')
slyfox1186_blacklist_location = os.path.join(
    pihole_location, 'slyfox1186-blacklist.txt')

db_exists = False
sqliteConnection = None
cursor = None

blacklist_remote = set()
blacklist_local = set()
blacklist_slyfox1186_local = set()
blacklist_old_slyfox1186 = set()

os.system('clear')
print('This script should only remove domains that were added by itself.')
print('Any other domains added personally by the user will remain uneffected.')

# Check for pihole path exsists
if os.path.exists(pihole_location):
    print('\n')
    print("[i] Pi-hole's path exists!")
else:
    print("[X] {} was not found!".format(pihole_location))
    print('\n')
    exit(1)

# Check for write access to /etc/pihole
if os.access(pihole_location, os.X_OK | os.W_OK):
    print("[i] Write access to {} verified!" .format(pihole_location))
    blacklist_str = fetch_blacklist_url(blacklist_remote_url)
    remote_blacklist_lines = blacklist_str.count('\n')
    remote_blacklist_lines += 1
else:
    print("[X] Write access is not available for {}. Please run the script as a privileged user..." .format(pihole_location))
    print('\n')
    exit(1)

# Determine whether we are using DB or not
if os.path.isfile(gravity_db_location) and os.path.getsize(gravity_db_location) > 0:
    db_exists = True
    print('[i] Succesfully located the Gravity database.')

    remote_sql_str = fetch_blacklist_url(remote_sql_url)
    remote_sql_lines = remote_sql_str.count('\n')
    remote_sql_lines += 1

    if len(remote_sql_str) > 0:
        print("[i] {} domains were discovered!" .format(remote_blacklist_lines))

    else:
        print('[X] No remote SQL queries were found!')
        print('\n')
        exit(1)
else:
    print('[i] Legacy Pi-hole detected ( older than v5.0)!')

if blacklist_str:
    blacklist_remote.update(x for x in map(
        str.strip, blacklist_str.splitlines()) if x and x[:1] != '#')
else:
    print('[X] No remote domains found!')
    print('\n')
    exit(1)

if db_exists:
    # Create a DB connection
    print("[i] Connecting to Gravity's database...")

    try:
        sqliteConnection = sqlite3.connect(gravity_db_location)
        cursor = sqliteConnection.cursor()
        print("[i] Successfully connected to Gravity's database!")
        total_domains = cursor.execute(" SELECT * FROM domainlist WHERE type = 1 AND comment LIKE '%SlyEBL%' ")

        totalDomains = len(total_domains.fetchall())
        print("[i] {} domains in the updated blacklist were added by this script." .format(totalDomains))
        print("[i] Removing domains from Gravity's database...")
        cursor.execute (" DELETE FROM domainlist WHERE type = 1 AND comment LIKE '%SlyEBL%' ")

        sqliteConnection.commit()

        # We only removed domains we added so use total_domains
        print("[i] There were {} domains removed from Gravity." .format(totalDomains))
        remaining_domains = cursor.execute(" SELECT * FROM domainlist WHERE type = 1 OR type = 3 ")
        print("[i] {} domains remain in Gravity's blacklist." .format(len(remaining_domains.fetchall())))
        cursor.close()

    except sqlite3.Error as error:
        print("[X] Failed to remove domains from Gravity's database!", error)
        print('\n')
        exit(1)

    finally:
        if (sqliteConnection):
            sqliteConnection.close()

            print("[i] The connection to the Gravity database has closed!")
            print('[i] Wait for Pi-hole to reboot...')
            restart_pihole(args.docker)
            print('\n')
            print('[i] The Exact Blacklist filters have been removed from Gravity!')

else:
    if os.path.isfile(gravity_blacklist_location) and os.path.getsize(gravity_blacklist_location) > 0:
        print('[i] Collecting existing entries from blacklist.txt')
        with open(gravity_blacklist_location, 'r') as fRead:
            blacklist_local.update(x for x in map(
                str.strip, fRead) if x and x[:1] != '#')

    if blacklist_local:
        print("[i] {} existing blacklisted identified." .format(len(blacklist_local)))

        if os.path.isfile(slyfox1186_blacklist_location) and os.path.getsize(slyfox1186_blacklist_location) > 0:
            print('[i] Existing slyfox1186-blacklist installation located.')
            with open(slyfox1186_blacklist_location, 'r') as fOpen:
                blacklist_old_slyfox1186.update(x for x in map(
                    str.strip, fOpen) if x and x[:1] != '#')

                if blacklist_old_slyfox1186:
                    blacklist_local.difference_update(blacklist_old_slyfox1186)

            os.remove(slyfox1186_blacklist_location)

        else:
            print('[i] Removing the blacklists now...')
            blacklist_local.difference_update(blacklist_remote)

    print("[i] Adding exsisting {} domains to {}" .format(
        len(blacklist_local), gravity_blacklist_location))
    with open(gravity_blacklist_location, 'w') as fWrite:
        for line in sorted(blacklist_local):
            fWrite.write("{}\n".format(line))

    print('[i] Wait for Pi-hole to reboot...')
    restart_pihole(args.docker)                                                    
    print('[i] The Exact Blacklist filters have been removed from Gravity!')
