#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK

# This script collects candle-lighting times from hebcal.com, weather
# reports from openweathermap.org, and sends an SMS to every subscriber
# from the Eruv Alerts Google Spreadsheet, based on the city.

# Imports:
import random
from random import randint
from time import sleep
import urllib.request
import json
import argparse
import sys

# 3rd party additional imports:
import argcomplete
from twilio.rest import Client
import gspread
from oauth2client.service_account import ServiceAccountCredentials

def extract_values(obj, key):
    """This function, being data-agnostic, extracts all key-values found in any multilevel JSON file, without knowing the order/hierarchy of the data.
    Obtained from: https://hackersandslackers.com/extract-data-from-complex-json-python/
    Pull all values of specified key from nested JSON."""
    arr = []

    def extract(obj, arr, key):
        """Recursively search for values of key in JSON tree."""
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, (dict, list)):
                    extract(v, arr, key)
                elif k == key:
                    arr.append(v)
        elif isinstance(obj, list):
            for item in obj:
                extract(item, arr, key)
        return arr
    results = extract(obj, arr, key)
    return results


def shorten_message(message):
    """This function recursively tries to shorten a message
    to under 160 characters"""
    if len(message) <= 160:
        return message
    else:
        if ' (50 min)' in message:
            return shorten_message(message.replace(' (50 min)', ''))
        else:
            # Warn if message still exceeds 160 characters:
            print(
                'Message for ' +
                city +
                ' exceeds 160 character limit!\nMessage: ' +
                message)
            return message

def army_to_meridian(input_time):
    if 'am' in input_time.lower() or 'pm' in input_time.lower():
        return input_time

    # Count occurrence of colons (to detect seconds):
    colon_count = input_time.count(':')
    time_split = input_time.split(':')
    hours = int(time_split[0])
    minutes = int(time_split[1])
    seconds = 0
    if colon_count == 2:
        seconds = int(time_split[2])
    meridian = ' AM'
    if hours >= 12:
        meridian = ' PM'
        hours -= 12
    if hours == 0:
        hours = 12
    return str(hours) + ':' + str(minutes).zfill(2) + (':' + str(seconds).zfill(2) if seconds != 0 else '') + meridian


# Define a list of random greetings to reduce spam detection and add variety:
greetings = ['a great', 'a wonderful', 'an amazing', 'a good']

# Initialize argument interpretation:
parser = argparse.ArgumentParser(
    description='This script sends SMS messages via Twilio to subscribers on a Google Sheet.')
parser.add_argument(
    '--append',
    action='append',
    help='Append a custom message to the end of the generated message (it is appended after the donate argument if both are requested).')
parser.add_argument(
    '--available-cities',
    action='store_true',
    help='Return a list of all available cities.')
parser.add_argument(
    '--blacklist',
    nargs='+',
    help='Append a list of cities (space delimited) to skip alerting (cities with 2+ names should be enclosed in quotes). Available cities can be found using the --available-cities flag. This argument will override the whitelist argument.')
parser.add_argument(
    '--custom-message',
    action='append',
    required='--phone' in sys.argv,
    help='Broadcast a custom message (ie: service announcements). This will override and disable candle-lighting, Havdalah, and weather reports (even forced). Donate and append argument can still be used.')
parser.add_argument(
    '--delayed',
    action='store_true',
    help='Slowly send out each SMS between 0 - 2 seconds (randomized).')
parser.add_argument(
    '--donate',
    action='store_true',
    help='Append a reminder to donate for select cities.')
parser.add_argument(
    '--include-whatsapp',
    action='store_true',
    help='Send SMS messages to WhatsApp numbers as well. These numbers normally do not receive SMS alerts.')
parser.add_argument(
    '--no-candlelighting',
    action='store_true',
    help='Skip appending candle-lighting times.')
parser.add_argument(
    '--no-havdalah',
    action='store_true',
    help='Skip appending havdalah times.')
parser.add_argument(
    '--no-weather',
    action='store_true',
    help='Skip checking for and reporting any weather updates. This will override the force-weather argument.')
parser.add_argument(
    '--phone',
    action='append',
    help='Sends an SMS to a single phone number instead of a group. This argument requires a custom message as well.')
parser.add_argument(
    '--test',
    action='store_true',
    help='Test run without actually sending.')
parser.add_argument(
    '-v',
    '--verbose',
    action='store_true',
    help='Verbose output. Useful for debugging.')
parser.add_argument(
    '--weather',
    action='store_true',
    help='Adds the weather to be reported and warn recipients.')
parser.add_argument(
    '--whitelist',
    nargs='+',
    help='Append a list of cities (space delimited) to only alert (cities with 2+ names should be enclosed in quotes). All other cities will be skipped. Available cities can be found using the --available-cities flag. The blacklist argument will override this.')
argcomplete.autocomplete(parser)
arguments = parser.parse_args()

# Display test mode warning:
if arguments.test:
    print('Test mode is on. Nothing will actually be sent.\n')

# Dispaly additional information if verbose requested:
if arguments.verbose:

    # Display ignored cities:
    if arguments.blacklist and not arguments.whitelist:
        print('Cities that will be skipped: ' +
              str([x.title() for x in arguments.blacklist]) + '\n')

    # Display whitelisted cities:
    if arguments.whitelist:
        if arguments.blacklist:
            print('Only these cities will be notified: ' +
                str(list(set([x.title() for x in arguments.whitelist]) -
                set([x.title() for x in arguments.blacklist]))) + '\n')
        else:
              print('Only these cities will be notified: ' +
                    str([x.title() for x in arguments.whitelist]) + '\n')

    # Display custom message:
    if arguments.custom_message:
        if arguments.append:
            print('A custom & appended message will be sent out instead!\n')
        else:
            print('A custom message will be sent out instead!\n')

    # Display appended message:
    if arguments.append and not arguments.custom_message:
        print('An appended message will be sent out along with the regular message!\n')

# Google Authentication from external JSON file:
scope = ['https://spreadsheets.google.com/feeds',
         'https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_name(
    'keys/google_auth.json', scope)
gclient = gspread.authorize(creds)
if arguments.verbose:
    print('Google Authenticated successfully.\n')

# Twilio Authentication from external JSON file:
with open('keys/twilio_auth.json') as file:
    twilio_file = json.load(file)
client = Client(twilio_file['account-sid'], twilio_file['password'])
if arguments.verbose:
    print('Twilio Authenticated successfully.\n')

# Load Open Weather Map Authentication from external JSON file:
with open('keys/open_weather_map.json') as file:
    open_weather_map = json.load(file)

# Send single SMS and exit:
if arguments.phone:
    message = ''.join(str(elem) for elem in arguments.custom_message)

    # Append donate message if requested (links may be flagged as spam):
    if arguments.donate:
        message = message + ' Please visit bit.ly/nmberuv to cover the costs.'

    # Add appended message if requested:
    if arguments.append:
        message = message + ' ' + ''.join(str(elem) for elem in arguments.append).strip()

    # Sanitize the phone number from special characters:
    clean_number = '+1' + str(
        ''.join(str(elem) for elem in arguments.phone)).replace("-", "").replace(" ", "").replace("(", "").replace(")", "").replace(".", "").replace("_", "")
    if arguments.test:
        print('"' + message + '" would have been sent to: ' + clean_number)
    else:
        twilio_message = client.messages.create(
            to=clean_number, from_=twilio_file['phone'], body=message)
        print('"' + message + '" was sent to: ' + clean_number)
    quit()

# Load lists from sheets:
subscriber_sheet = gclient.open('Eruv List').worksheet('Subscribers')
rabbi_sheet = gclient.open('Eruv List').worksheet('Rabbis')
status_sheet = gclient.open('Eruv List').worksheet('Status')
if arguments.verbose:
    print('Google Sheets loaded successfully.\n')

# Create arrays of all elements from the sheets. Skip top row (Timestamp,
# Phone Number, City, Rabbi's City, Zip Code):
all_numbers = subscriber_sheet.col_values(2)[1:]
all_user_cities = subscriber_sheet.col_values(3)[1:]
whatsapp_list = subscriber_sheet.col_values(4)[1:]
all_rabbi_cities = rabbi_sheet.col_values(3)[1:]
all_rabbi_zipcodes = rabbi_sheet.col_values(4)[1:]
all_cities = status_sheet.col_values(1)
city_statuses = status_sheet.col_values(2)
if arguments.verbose:
    print('Cities loaded successfully.\n')

# Display a list of cities to user and exit if requested:
if arguments.available_cities:
    print(all_cities)
    quit()

# For each city in Status Sheet:
city_index = 0

for city in all_cities:

    # Skip if city is being ignored (case insensitive):
    if arguments.blacklist:
        if city.lower() in [x.lower() for x in arguments.blacklist]:
            print('\nSkipping ' + str(city) + " because it's blacklisted!\n")
            city_index += 1
            continue

    # Skip if whitelist enabled and city isn't whitelisted (case insensitive):
    if arguments.whitelist:
        if not city.lower() in [x.lower() for x in arguments.whitelist]:
            print(
                '\nSkipping ' +
                str(city) +
                " because it isn't whitelisted!\n")
            city_index += 1
            continue

    # Skip if the city status is Pending:
    if city_statuses[city_index] == 'Pending':
        print('\nSkipping ' + str(city) + " because it's still pending!\n")
        city_index += 1
        continue

    # Get zipcode of city:
    zip_index = 0
    zipcode = 0
    for rabbi_city in all_rabbi_cities:
        if rabbi_city == city:
            zipcode = all_rabbi_zipcodes[zip_index]
            break
        zip_index += 1

    # Catch invalid Zip Code:
    if zipcode == 0:
        print('\nInvalid zipcode detected for ' + city + '!\n')
        quit()

    # Get Candle-lighting, Havdalah, and Parsha/Chag from hebcal.com:
    hebcal_URL = 'https://www.hebcal.com/shabbat/?cfg=json&zip=' + \
        str(zipcode) + '&m=50&a=on'
    response = ''

    # Skip checking times if requested:
    if (arguments.no_candlelighting and arguments.no_havdalah) or arguments.custom_message:
        print('\nSkipping candlelighting and Havdalah times!\n')
    else:
        response = json.loads(
            urllib.request.urlopen(
                hebcal_URL,
                timeout=15).read().decode('utf-8'))

    # Find first occurrence of Candle-lighting from JSON:
    candle_lighting = ''
    if response != '':
        candle_lighting = [
            i for i in extract_values(
                response,
                'title') if 'Candle' in i][0]

    # Detects and converts army times to Meridian:
    if candle_lighting != '':
        candle_lighting = candle_lighting.rsplit(' ', 1)[0] + ' ' + army_to_meridian(candle_lighting.rsplit(' ', 1)[1])
        candle_lighting += '. '

    # Skip candlelighting if requested:
        if arguments.no_candlelighting:
            candle_lighting = ''

    # Find first occurrence of Havdalah from JSON only if Havdalah exists:
    havdalah = ''

    # Verify there's a Havdalah entry first:
    if not arguments.no_havdalah and len([i for i in extract_values(response, 'title') if 'Havdalah' in i]) > 0:
        havdalah = [
            i for i in extract_values(
                response,
                'title') if 'Havdalah' in i][0]

        # Detects and converts army times to Meridian:
        havdalah = havdalah.rsplit(' ', 1)[0] + ' ' + army_to_meridian(havdalah.rsplit(' ', 1)[1])

        havdalah = havdalah + '. '

    # Store if holiday:
    holiday = ''

    # Check if any Parsha is listed in JSON:
    if [i for i in extract_values(response, 'title') if 'Parsha' in i]:

        # Find first occurrence of Parsha from JSON:
        parsha = [
            i for i in extract_values(
                response,
                'title') if 'Parsha' in i][0] + '.'

    else:

        # No Parsha listed; assume it's a holiday:
        parsha = 'Chag Somayach!'
        holiday = ' and Yom Tov'

    # If there's a thunderstorm or tornado, warn users to be vigilant:
    weather_response = ''
    temperature = ''
    humidity = ''
    if arguments.no_weather or arguments.custom_message:
        print('\nNo weather is being reported!\n')
    else:
        weather_response = json.loads(
            urllib.request.urlopen(
                'https://api.openweathermap.org/data/2.5/weather?zip=' +
                str(zipcode) +
                ',us&appid=' +
                open_weather_map['api-key'],
                timeout=15).read().decode('utf-8'))
        temperature = 'Temperature: ' + \
            str(int(1.8 * (weather_response['main']['temp'] - 273.15) + 32)) + 'F'
        humidity = str(weather_response['main']['humidity']) + '% humid'
    if arguments.verbose and not arguments.no_weather and not arguments.custom_message:
        print('Reported temperature for ' + city + ': ' + temperature + '\n')
        print('Reported humidity for ' + city + ': ' + humidity + '\n')

    # Prequel & sequel will change if a storm is detected:
    prequel = ' The '
    sequel = ''

    if [i for i in extract_values(weather_response, 'description') if 'thunderstorm' in i or 'tornado' in i] or arguments.weather and not arguments.no_weather:
        print('Weather will be reported!\n')
        print('Reported temperature for ' + city + ': ' + temperature + '\n')
        print('Reported humidity for ' + city + ': ' + humidity + '\n')
        prequel = ' As of now, the '
        sequel = '. If winds exceed 35 mph, consider the Eruv down'

    # Loop through all users from city and send:
    user_index = 0
    population = 0
    for city_found in all_user_cities:
        for city_item in [x.strip() for x in city_found.split(',')]:
            if city == city_item:

                # Skip if WhatsApp user, unless requested:
                if whatsapp_list[user_index].lower() == 'whatsapp':
                    if arguments.include_whatsapp:
                        print('\nSending SMS to a WhatsApp number!\n')
                    else:
                        continue

                # Final message:
                message = parsha + prequel + city + ' Eruv is ' + city_statuses[city_index] + sequel + '. ' + candle_lighting + havdalah + (
                    'Have ' + random.choice(greetings) + ' Shabbos' + holiday + '!' if sequel == '' else '')

                # Try to shorten the message & remove whitespace if necessary:
                message = shorten_message(message).strip()

                # Override message with custom message if requested:
                if arguments.custom_message:
                    message = ''.join(str(elem) for elem in arguments.custom_message)

                # Append donate message if requested (links may be flagged as spam):
                if arguments.donate:
                    message = message + ' Please visit bit.ly/nmberuv to cover the costs.'

                # Add appended message if requested:
                if arguments.append:
                    message = message + ' ' + ''.join(str(elem) for elem in arguments.append).strip()

                # Sanitize the phone number from special characters:
                clean_number = '+1' + str(
                    all_numbers[user_index]).replace("-", "").replace(" ", "").replace("(", "").replace(")", "").replace(".", "").replace("_", "")

                # Display and send:
                if arguments.verbose:
                    print(clean_number + ' > ' + message)

                # Send if no testing argument:
                if not arguments.test:
                    twilio_message = client.messages.create(
                        to=clean_number, from_=twilio_file['phone'], body=message)

                # Wait a random amount of seconds between sending (0 - 2
                # seconds):
                if arguments.delayed:
                    sleep(randint(0, 2))

                # Keep track of total # of users:
                population += 1

        # Keep track of current index of user:
        user_index += 1

    print('\n' +
        str(population) +
        ' users ' +
        ('would have been ' if arguments.test else '') +
        'notified' +
        (': "' + message + '"' if arguments.custom_message else ' that ' + city + ' is ' + city_statuses[city_index] + '.') + '\n')
    city_index += 1
