'''AJ Estes SI 206 Final Project'''

'''
The purpose of this project is to use YouTube API in order to output an image file
that shows the total number of comments for a Youtube channel's videos by the total
length of the video, segmented into 5 categories: Less Than 2 Minutes, Between 2 and 
4 Minutes, Between 4 and 6 Minutes, Between 6 and 8 Minutes, and Greater Than 8 Minutes,
as a bar chart.
'''

'''Import statements required to run the project.'''
import os
import google.oauth2.credentials
import google_auth_oauthlib.flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow
from urllib.request import urlopen
import json
import sqlite3
import requests
import re
import matplotlib.pyplot as plt
import csv

'''
The CLIENT_SECRETS_FILE variable specifies the name of a file that contains
the OAuth 2.0 information for this application, including its client_id and
client_secret.
'''
CLIENT_SECRETS_FILE = "client_secret.json"

'''
This OAuth 2.0 access scope allows for full read/write access to the
authenticated user's account and requires requests to use an SSL connection.
'''
SCOPES = ['https://www.googleapis.com/auth/youtube.force-ssl']
API_SERVICE_NAME = 'youtube'
API_VERSION = 'v3'

def get_authenticated_service():
  flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
  credentials = flow.run_console()
  return build(API_SERVICE_NAME, API_VERSION, credentials = credentials)

def print_response(response):
  print(response)

'''
Build a resource based on a list of properties given as key-value pairs.
Leave properties with empty values out of the inserted resource.
'''
def build_resource(properties):
  resource = {}
  for p in properties:
    '''
    Given a key like "snippet.title", split into "snippet" and "title", where
    "snippet" will be an object and "title" will be a property in that object.
    '''
    prop_array = p.split('.')
    ref = resource
    for pa in range(0, len(prop_array)):
      is_array = False
      key = prop_array[pa]

      '''
      For properties that have array values, convert a name like
      "snippet.tags[]" to snippet.tags, and set a flag to handle
      the value as an array.
      '''
      if key[-2:] == '[]':
        key = key[0:len(key)-2:]
        is_array = True

      if pa == (len(prop_array) - 1):
        '''Leave properties without values out of inserted resource.'''
        if properties[p]:
          if is_array:
            ref[key] = properties[p].split(',')
          else:
            ref[key] = properties[p]
      elif key not in ref:

        '''
        For example, the property is "snippet.title", but the resource does
        not yet have a "snippet" object. Create the snippet object here.
        Setting "ref = ref[key]" means that in the next time through the
        "for pa in range ..." loop, we will be setting a property in the
        resource's "snippet" object.
        '''
        ref[key] = {}
        ref = ref[key]
      else:

        '''
        For example, the property is "snippet.description", and the resource
        already has a "snippet" object.
        '''
        ref = ref[key]
  return resource

'''
Remove keyword arguments that are not set.
'''
def remove_empty_kwargs(**kwargs):
  good_kwargs = {}
  if kwargs is not None:
    for key, value in kwargs.items():
      if value:
        good_kwargs[key] = value
  return good_kwargs

def videos_list_by_id(client, **kwargs):
  kwargs = remove_empty_kwargs(**kwargs)

  response = client.videos().list(
    **kwargs
  ).execute()

  return response

'''
Function get_all_video_in_channel that takes a Youtube Channel ID 
as an input and outputs a list of all of the the channel's Video IDs.
'''
def get_all_video_in_channel(channel_id):
    api = ''

    videoUrl = ''
    searchUrl = 'https://www.googleapis.com/youtube/v3/search?'

    '''
    firstURL uses the Youtube search function to get the channel's information
    and to limit the results requested to 25.
    '''
    firstUrl = searchUrl+'key={}&channelId={}&part=snippet,id&order=date&maxResults=25'.format(api, channel_id)

    videoLinks = []
    url = firstUrl
    while True:
        inp = urlopen(url)
        resp = json.load(inp)

        for i in resp['items']:
            if i['id']['kind'] == "youtube#video":
                videoLinks.append(videoUrl + i['id']['videoId'])

        try:
            next_page_token = resp['nextPageToken']
            url = firstUrl + '&pageToken={}'.format(next_page_token)
        except:
            break
    return videoLinks

'''
Function get_stats takes in an input of a list of Youtube Video IDs, a dictionary cacheDict 
to cache video information, and a file fname to output the dictionary to a json file. The function
outputs a dictionary, where the keys are the Video Ids, and the values are a list of dictionaries of 
the statistics for the video.
'''
def get_stats(video_list, cacheDict, fname):
  for x in video_list:
    if x not in cacheDict:
      key = videos_list_by_id(client,
        part='contentDetails,statistics',
        id=x)['items'][0]['id']

      commentCount = videos_list_by_id(client,
        part='contentDetails,statistics',
        id=x)['items'][0]['statistics']

      duration = videos_list_by_id(client,
        part='contentDetails,statistics',
        id=x)['items'][0]['contentDetails']

      cacheDict[key]=(commentCount,duration)
      fileUpdate = open(fname, 'w')
      fileUpdate.write(json.dumps(cacheDict))
      fileUpdate.close()
  
  return cacheDict

'''
Function setUpYoutubeTable takes a dictionary where the keys are the Video Ids, 
and the values are a list of dictionaries of the statistics for the video, a sqlite3 
connection, and a conn.cursor(). This function then creates a sqlite table where the 
columns are the Youtube Video Id, the duration of that video, and the number of comments. 
'''
def setUpYoutubeTable(youtubeDictionary, conn, cur):
  conn = sqlite3.connect('youtube.sqlite')
  cur = conn.cursor()
  cur.execute('DROP TABLE IF EXISTS Youtube')
  cur.execute('CREATE TABLE Youtube(id TXT, commentCount INTEGER, duration TXT)')

  for x in youtubeDictionary.items():
    cur.execute('INSERT INTO Youtube(id, commentCount, duration) VALUES (?, ?, ?)', (str(x[0]), int(x[1][0]['commentCount']), str(x[1][1]['duration'])))
    conn.commit()

'''
Function getYoutubeDict takes in a sqlite connection as an input and selects the duration
and number of comments for each video. This function then puts this data into a dictionary
where the keys are the length of the video, which are as follows: Less Than 2 Minutes, Between 
2 and 4 Minutes, Between 4 and 6 Minutes, Between 6 and 8 Minutes, and Greater Than 8 Minutes.
The values for these keys are the total number of comments received for the videos. This is 
calculated by iterating through the sqlite data and using regular expressions to decode the 
given duration information from YouTube's API and adding each video's comment count to the total
number of comments for each key. This function returns a dictionary of the categories of video 
duration with their values being the total number of comments for each duration category.
'''
def getYoutubeDict(cur):
  cur.execute('SELECT duration, commentCount from Youtube')
  youtubeDict = {'Less Than 2 Minutes': 0, 'Between 2 and 4 Minutes': 0, 'Between 4 and 6 Minutes': 0, 'Between 6 and 8 Minutes': 0, 'Greater Than 8 Minutes': 0}

  for aVideo in cur:
    secondCheck = re.search(r'(?<=PT)(.*)(?=S)', aVideo[0])
    secondValue = secondCheck.group(0)

    if 'M' not in secondValue:
      youtubeDict['Less Than 2 Minutes'] += aVideo[1]

    minuteCheck = re.search(r'(?<=PT)(.*)(?=M)', aVideo[0])

    if minuteCheck is not None:
      minuteValue = minuteCheck.group(0)
    
    if int(minuteValue) >= 2 and int(minuteValue) < 4:
      youtubeDict['Between 2 and 4 Minutes'] += aVideo[1]

    if int(minuteValue) >= 4 and int(minuteValue) < 6:
      youtubeDict['Between 4 and 6 Minutes'] += aVideo[1]

    if int(minuteValue) >= 6 and int(minuteValue) < 8:
      youtubeDict['Between 6 and 8 Minutes'] += aVideo[1]

    if int(minuteValue) >= 8:
      youtubeDict['Greater Than 8 Minutes'] += aVideo[1]

  return(youtubeDict)

'''
Function drawBarChart takes in a dictionary of duration categories with their values being
the total number of comments for each category. This function then outputs an image of a bar
graph that displays the total number of comments for a youtube channel by video duration.
'''
def drawBarChart(youtubeDict):
  youtubeList = ['Less Than 2 Minutes', 'Between 2 and 4 Minutes', 'Between 4 and 6 Minutes', 'Between 6 and 8 Minutes', 'Greater Than 8 Minutes']
  dataList = []

  for video in youtubeList:
    dataList.append(youtubeDict[video])

  fig, ax = plt.subplots()

  ax.bar(range(0,5), dataList, 0.7, color = 'blue', edgecolor = 'black')
  ax.set_xticks(range(0,5))
  ax.set_xticklabels(tuple(youtubeList))
  ax.set(xLabel = 'Video Duration', yLabel = 'Total Comments', title = 'Total Number of Comments for a Youtube Channel by Video Duration - AJ Estes')
  fig.savefig("bar.png")
  plt.show()

'''
Function createCSV takes in the dictionary of the 5 duration categories and their total 
amount of comments as an input and creates a CSV file that displays them by duration and 
total amount of comments.
'''
def createCSV(finalDict):
  with open('YoutubeDict.csv', 'w') as csv_file:
    writer = csv.DictWriter(csv_file, fieldnames = ["Duration", "Number of Comments"])
    writer.writeheader()

    writer = csv.writer(csv_file)
    for key, value in finalDict.items():
       writer.writerow([key, value])

'''
Function runProject takes in the a Youtube Channel's ID and passes it through all of the above
functions in order to reach the end goal, which is to create a bar graph image file that displays
the total number of comments for a youtube channel by video duration. This function then outputs a 
message confirming that the function has run.
'''
def runProject(YoutubeID):
  fname = "youtube_cache.json"

  try:
    cache_file = open(fname,'r')
    cache_contents = cache_file.read()
    cache_file.close()
    cacheDict = json.loads(cache_contents)
  except:
    cacheDict = {}

  videoList = get_all_video_in_channel(YoutubeID)

  conn = sqlite3.connect('youtube.sqlite')
  cur = conn.cursor()
  youtubeDictionary = get_stats(videoList, cacheDict, fname)
  setUpYoutubeTable(youtubeDictionary, conn, cur)

  drawBarChart(getYoutubeDict(cur))
  createCSV(getYoutubeDict(cur))
  message = 'See the image file for results.'

  return message

'''
The following line of code runs the entire project. The variable ArianaGrandeChannelId is the 
YouTube Channel ID for pop-sensation Ariana Grande and is used in the function runProject in order
to return a bar graph image file that displays the total number of comments for Ariana Grande's 
channel by video duration.
'''
if __name__ == '__main__':

  '''
  When running locally, disable OAuthlib's HTTPs verification. When
  running in production *do not* leave this option enabled.
  '''
  os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
  client = get_authenticated_service()

  ArianaGrandeChannelId = 'UC9CoOnJkIBMdeijd9qYoT_g'
  print(runProject(ArianaGrandeChannelId))