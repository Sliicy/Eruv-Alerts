#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# This script collects candle-lighting times from hebcal.com, weather reports from openweathermap.org, and sends an SMS to every subscriber from the Eruv Alerts Google Spreadsheet, based on the city.

# Imports:
from twilio.rest import Client
import gspread, argparse
from oauth2client.service_account import ServiceAccountCredentials
import urllib.request, json, argparse

# Add random time delay to prevent being flagged.
from random import randint
from time import sleep
import random

# This function, being data-agnostic, extracts all key-values found in any multilevel JSON file, without knowing the order/hierarchy of the data:
def extract_values(obj, key):
    """Pull all values of specified key from nested JSON."""
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

# Initialize argument interpretation:
parser = argparse.ArgumentParser(description='This script sends SMS messages via Twilio to subscribers on a Google Sheet.')
parser.add_argument('--test', help='Test run without actually sending.', action='store_true')
parser.add_argument('-v', '--verbose', help='Helpful for debugging.', action='store_true')
arguments = parser.parse_args()


# Google Authentication from external JSON file:
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_name('keys/google-auth.json', scope)
gclient = gspread.authorize(creds)
if arguments.verbose: print('Google Authenticated successfully.\n')


# Twilio Authentication from external JSON file:
with open('keys/twilio_auth.json') as file:
  twilio_file = json.load(file)
client = Client(twilio_file['account-sid'], twilio_file['password'])
if arguments.verbose: print('Twilio Authenticated successfully.\n')

# Load Open Weather Map Authentication from external JSON file:
with open('keys/open_weather_map.json') as file:
    open_weather_map = json.load(file)


# Load lists from sheets:
subscriberSheet = gclient.open('Eruv List').worksheet('Subscribers')
rabbiSheet = gclient.open('Eruv List').worksheet('Rabbis')
statusSheet = gclient.open('Eruv List').worksheet('Status')
if arguments.verbose: print('Google Sheets loaded successfully.\n')


# Create arrays of all elements from the sheets. Skip top row (Timestamp, Phone Number, City, Rabbi's City, Zip Code):
allNumbers = subscriberSheet.col_values(2)[1:]
allUserCities = subscriberSheet.col_values(3)[1:]
allRabbiCities = rabbiSheet.col_values(3)[1:]
allRabbiZips = rabbiSheet.col_values(4)[1:]
allCities = statusSheet.col_values(1)
cityStatuses = statusSheet.col_values(2)
if arguments.verbose: print('Cities loaded successfully.\n')

# Define a list of random greetings to reduce spam detection and add variety:
greetings = ['a great', 'a wonderful', 'an amazing', 'a good']

# For each city in Status Sheet:
cityIndex = 0
for city in allCities:

    # Skip if the city status is Pending:
    if cityStatuses[cityIndex] == 'Pending':
        cityIndex += 1
        continue

    # Get zipcode of city:
    zipIndex = 0
    zipcode = 0
    for rabbiCity in allRabbiCities:
        if rabbiCity == city:
            zipcode = allRabbiZips[zipIndex]
            break
        zipIndex += 1

    # Catch invalid Zip Code:
    if zipcode == 0:
        print('\nInvalid zipcode detected for ' + city + '!\n')
        quit()

    # Get Candle-lighting, Havdalah, and Parsha/Chag from hebcal.com:
    hebcalURL = 'https://www.hebcal.com/shabbat/?cfg=json&zip=' + str(zipcode) + '&m=50&a=on'
    response = json.loads(urllib.request.urlopen(hebcalURL, timeout=15).read().decode('utf-8'))

    # Find first occurrence of Candle-lighting from JSON:
    candleLighting = [i for i in extract_values(response, 'title') if 'Candle' in i][0]

    # Find first occurrence of Havdalah from JSON only if Havdalah exists:
    havdalah = ''

    # Verify there's a Havdalah entry first:
    if len([i for i in extract_values(response, 'title') if 'Havdalah' in i]) > 0:
        havdalah = [i for i in extract_values(response, 'title') if 'Havdalah' in i][0]
        havdalah = havdalah + '. '
    if len(havdalah) == 0: print('No Havdalah time detected!')

    # No holiday by default:
    holiday = ''

    # Check if any Parsha is listed in JSON:
    if [i for i in extract_values(response, 'title') if 'Parsha' in i]:

        # Find first occurrence of Parsha from JSON:
        parsha = [i for i in extract_values(response, 'title') if 'Parsha' in i][0] + '.'

    else:

        # No Parsha listed; assume it's a holiday:
        parsha = 'Chag Somayach!'
        holiday = ' and Yom Tov'

    # If there's a thunderstorm or tornado, warn users to be vigilant:
    weatherResponse = json.loads(urllib.request.urlopen('https://api.openweathermap.org/data/2.5/weather?zip=' + str(zipcode) + ',us&appid=' + open_weather_map['api-key'], timeout=15).read().decode('utf-8'))
    temperature = 'Temperature: ' + str(int(1.8 * (weatherResponse['main']['temp'] - 273.15) + 32)) + 'F'
    humidity = str(weatherResponse['main']['humidity']) + '% humid'

    # Prequel & sequel change if there's a storm:
    prequel = ' The '
    sequel = ''

    if [i for i in extract_values(weatherResponse, 'description') if 'thunderstorm' in i or 'tornado' in i]:
        prequel = ' As of now, the '
        sequel = 'If winds exceed 35 mph, consider the Eruv down. '

    # Loop through all users from city and send:
    userIndex = 0
    userCount = 0
    for cityFound in allUserCities:
        for cityItem in [x.strip() for x in cityFound.split(',')]:
            if city == cityItem:

                # Final message:
                havdalah = ''
                message = parsha + prequel + city + ' Eruv is ' + cityStatuses[cityIndex] + '. ' + sequel + candleLighting + '. ' + havdalah + ('Have ' + random.choice(greetings) + ' Shabbos' + holiday + '!' if sequel == '' else '.')

                # Try to shorten the message if necessary:
                if len(message) > 160: message = message.replace(' (50 min)', '')

                # Warn if message still exceeds 160 characrters:
                if len(message) > 160:
                    print('Message for ' + city + ' exceeds 160 character limit!\nMessage: ' + message)
                    quit()

                # Add optional parameters to select cities: (links may be flagged as spam)
                #if city == 'North Miami Beach': message = message + ' Please visit bit.ly/nmberuv to cover the costs.'

                # Sanitize the phone number from special characters:
                cleanNumber = '+1' + str(allNumbers[userIndex]).replace("-", "").replace(" ", "").replace("(", "").replace(")", "").replace(".", "").replace("_", "")

                # Display and send:
                if arguments.verbose: print(cleanNumber + ' > ' + message)

                # Send if no testing argument:
                if not arguments.test: twilio_message = client.messages.create(to=cleanNumber, from_=twilio_file['phone'], body=message)

                # Wait a random amount of seconds between sending (0 - 2 seconds):
                #sleep(randint(0,2))

                userCount += 1
        userIndex += 1
    print('\n' + str(userCount) + ' users notified in ' + city + '.\n')
    cityIndex += 1
