import spotipy
import pandas as pd
from pandas import read_csv
import numpy as np
from ast import literal_eval

from spotipy.oauth2 import SpotifyOAuth
from sklearn.neighbors import KNeighborsClassifier
from sklearn.ensemble import RandomForestClassifier


# cleans up the genre column
def genre_cleaner(genres):
  genre = genres[0].lower()
  genre = genre.split(" ")
  return genre[len(genre)-1]

# cleans up track feature response to get only necessary features
def extract_features(track_features):
  features_list = ["acousticness", "danceability", "duration_ms", "energy",
                   "instrumentalness", "liveness", "loudness", "speechiness", "tempo", "valence"]
  tracks = []
  for track_feature in track_features:
    track = []
    for feature in features_list:
      track.append(track_feature[feature])

    tracks.append(track)

  return np.array(tracks)

# takes in list of tracks and returns list of track ids
def get_track_ids(track_list):
  track_ids = []
  for track in track_list:
    track_ids.append(track['track']['id'])

  return track_ids

# takes in list of playlist objects, returns dictionary of {playlist names: playlist ids}
def get_playlist_names(playlists):
  playlist_dict = {}
  playlist_arr = []
  for playlist in playlists:
    playlist_dict[playlist['name']] = playlist['id']

  return playlist_dict

# reads song data (data_w_genres.csv) obtained from https://www.kaggle.com/yamaerenay/spotify-dataset-19212020-160k-tracks
x_data = read_csv('./data.csv', converters={'genres': eval})

# BEGIN WRANGLING THE DATA
x_data.drop(columns=['artists', 'key', 'mode', 'count', 'popularity'], inplace=True)
x_data = x_data[x_data['genres'].map(lambda d: len(d)) > 0]
x_data['genres'] = x_data['genres'].apply(genre_cleaner)

# remove genres that have less tracks than min_tracks
genre_counts = x_data['genres'].value_counts()
min_tracks = 100

for index, row in genre_counts.iteritems():
  if row < min_tracks:
    x_data.drop(x_data.index[x_data['genres'] == index], inplace=True)

# split the data to make a classification set
y_data = x_data.pop('genres')

# fit a multiclass random forest classifier with the track data
rf = RandomForestClassifier(max_depth=10, max_features='sqrt')
rf.fit(x_data, y_data)


# Spotify App Info
CLIENT_ID = ''
CLIENT_SECRET = ''
scope = "user-library-read, playlist-modify-public, playlist-modify-private, playlist-read-private, playlist-read-collaborative"

# set up oauth and obtain key
auth_manager = SpotifyOAuth(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, redirect_uri='https://google.com', scope=scope)
sp = spotipy.Spotify(auth_manager=auth_manager)

user_id = sp.me()['id']

# get a dictionary of all user's playlists
all_messy_playlists = []
offset = 0
while True:
  messy_playlists = sp.user_playlists(user_id, limit=50, offset=offset)['items']
  if len(messy_playlists) < 1: break
  all_messy_playlists += messy_playlists
  offset += len(messy_playlists)

all_playlists = get_playlist_names(all_messy_playlists)
new_playlists = {}


# classify tracks and add them to playlists based on their genre
# offset: track to start from in library
# num_liked_tracks: number of tracks to store in playlists
offset = 900
start_point = offset
num_liked_tracks = 20
while offset < start_point + num_liked_tracks:
  # retrieve track IDs from user's saved library
  limit = 50 if (start_point + num_liked_tracks) - offset >= 50 else (start_point + num_liked_tracks) - offset
  track_list = sp.current_user_saved_tracks(limit=limit, offset=offset)['items']
  if len(track_list) < 1: break

  track_ids = get_track_ids(track_list)

  # obtain audio features from each track
  messy_track_features = sp.audio_features(track_ids)
  track_features = extract_features(messy_track_features)

  y_pred = rf.predict(track_features)

  # store track ids in dictionary based on their genre
  # key: genre, value: array of track ids of that genre
  genre_dict = {}
  for i, track_genre in enumerate(y_pred):
    track_id = track_ids[i]
    genre_ids = genre_dict.get(track_genre)
    if genre_ids:
      genre_ids.append(track_id)
    else:
      id_list = []
      id_list.append(track_id)
      genre_dict[track_genre] = id_list

  # creates new playlist for genre or adds new one if nonexistant or desire to make a new one? cut sizes down to certain # ?
  for genre, track_list in genre_dict.items():
    playlist_name = genre + ".py"
    playlist_id = all_playlists.get(playlist_name)

    if playlist_id is None:
      existing_playlist = new_playlists.get(playlist_name)

      if existing_playlist:
        playlist_id = existing_playlist
      else:
        created_playlist = sp.user_playlist_create(user_id, playlist_name, public=True, collaborative=False, description='')
        playlist_id = created_playlist['id']
        new_playlists[playlist_name] = playlist_id

    sp.playlist_add_items(playlist_id, track_list)

  offset += len(track_ids)
