# Eruv Alerts
This project sends an SMS to every subscriber from an Eruv Alerts Google Spreadsheet, based on the city's status.

## Requirements

The script requires both a Google Spreadsheet and a Twilio account to send SMS messages. Although not required, it also tries to use openweathermap.org for weather.

All of the authentication keys used should be saved in the keys/ folder. The example keys contained within are examples of what they should contain.

To generate Google Spreadsheet credentials, follow this tutorial:
https://gspread.readthedocs.io/en/latest/

These can be installed with pip:
```bash
pip3 install gspread twilio oauth2client
```

Finally, make the script executable:
```bash
chmod +x ./eruv_alerts.py
```
