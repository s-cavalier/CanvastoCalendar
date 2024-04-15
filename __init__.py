from datetime import datetime
import os.path
import json

from canvasapi import Canvas

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


SCOPES = ["https://www.googleapis.com/auth/calendar"]

if __name__ == "__main__":
    canvas_info = {}
    with open('canvas_login.json', 'r') as file:
        canvas_info = json.load(file)

    canvas = Canvas(canvas_info["api_url"], canvas_info["api_key"])

    courses = canvas.get_current_user().get_courses(enrollment_status='active')
    course_list = []

    for course in courses:
        try:
            course.name
        except AttributeError as err:
            continue
        ind = -1
        for i in reversed(range(len(course.name))):
            if course.name[i] == "-":
                ind = i
                break
        if course.name[ind + 2:] != canvas_info["current_unit"]: 
            continue
        c = {
            'name' : course.name[0:ind - 1],
            'assignments' : course.get_assignments(),
            'calendar' : None
        }
        course_list.append(c)

    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file( "credentials.json", SCOPES )
            creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open("token.json", "w") as token:
                token.write(creds.to_json())

    try:
        service = build("calendar", "v3", credentials=creds)
        
        # Get all calendars
        cal_ref = {}
        page_token = None
        while True:
            calendar_list = service.calendarList().list(pageToken=page_token).execute()
            for calendar_list_entry in calendar_list['items']:
                cal_ref[calendar_list_entry['summary']] = calendar_list_entry
            page_token = calendar_list.get('nextPageToken')
            if not page_token:
                break
        
        # Match classes to calendars or create new calendar?
        for course in course_list:
            if course['name'] in cal_ref:
                course['calendar'] = cal_ref[course['name']]
                print(course['name'] + ' calendar accessed.')
                continue
            inp = input(course['name'] + " has not been found in your calendars. Enter 'Y' to create a new one, or any other character to ignore.\n")
            if inp == "Y":
                calendar = {
                    "summary" : course['name']
                }
                created_calendar = service.calendars().insert(body=calendar).execute()
                course['calendar'] = created_calendar
        

        print("Calendar's accessed. Adding assignment information...\n")
        
        # Add assignments to corresponding calendars
        for course in course_list:
            # First check to make sure that we aren't adding already created events, if so only add if the due date has been changed
            # Grab all events
            if course['calendar'] == None:
                continue
            event_ref = {}
            matched_event = None
            page_token = None
            while True:
                events = service.events().list(calendarId=course['calendar']['id'], pageToken=page_token).execute()
                for event in events['items']:
                    event_ref[event['summary']] = event
                page_token = events.get('nextPageToken')
                if not page_token:
                    break
            for assignment in course['assignments']:
                if assignment.due_at == None:
                    print(assignment.name, end="")
                    print(" has no due date.")
                    continue
                if not assignment.name in event_ref:
                    ev = {
                        'summary' : assignment.name,
                        'description' : "Homework for " + course['name'],
                        'start' : {
                            'dateTime' : assignment.due_at
                        },
                        'end' : {
                            'dateTime' : assignment.due_at
                        }
                    }
                    ev = service.events().insert(calendarId=course['calendar']['id'], body=ev).execute()
                    print(assignment.name, end='')
                    print (' assignment created at: %s' % (ev['htmlLink']))
                    continue
                if assignment.name in event_ref:
                    if assignment.due_at == event_ref[assignment.name]['start']['dateTime']:
                        print(assignment.name, end='')
                        print(" already exists.")
                        continue
                    service.events().delete(calendarId=course['calendar']['id'], eventId=event_ref[assignment.name]['id']).execute()
                    ev = {
                        'summary' : assignment.name,
                        'description' : "Homework for " + course.name,
                        'start' : {
                            'dateTime' : assignment.due_at
                        },
                        'end' : {
                            'dateTime' : assignment.due_at
                        }
                    }
                    ev = service.events().insert(calendarId=course['calendar']['id'], body=ev).execute()
                    print(assignment.name, end='')
                    print (' assignment has been updated with a new due date at: %s' % (event['htmlLink']))
                    continue
            print('All assignments for ' + course['name'] + ' have been created.')
            print()
            
        print('')
        print('All assignments have been added. Press Enter to exit.')
        input()
    except HttpError as error:
        print(f"An error occurred: {error}")
