DEBUG = False

import feedparser
import codecs
from bs4 import BeautifulSoup
from PIL import Image
import requests
import time
import os 
import re
from PIL import Image
import hashlib
from datetime import datetime, timedelta
from xml.sax import saxutils
from flask import render_template

import shutil
from flask import Flask

FORCE_CACHE = False
DOWNLOAD_TIMEOUT = 15
MAX_IMAGES = 80
MAX_TITLE_LEN = 70
MAX_DESC_LEN = 200
NERD_DURATION = timedelta(days=1)

DEPLOY_DIRECTORY = 'docs/'
THUMBS_DIRECTORY = DEPLOY_DIRECTORY+'imgs/thumbs'
THUMBS_LINK_DIRECTORY = 'imgs/thumbs'

from cachecontrol import CacheControl
from cachecontrol.caches.file_cache import FileCache
session = CacheControl(requests.Session(), cache=FileCache('hackurls_cache'))

def cut_title(string):
	if len(string) > MAX_TITLE_LEN:
		return string[0:MAX_TITLE_LEN]+"..."
	else:
		return string

def cut_description(string):
	if len(string) > MAX_DESC_LEN:
		return string[0:MAX_DESC_LEN]+"..."
	else:
		return string
		
def cut_all_descriptions(entries):
	for entry in entries:
		entry.description = cut_description(entry.description)
	return entries
		
"""Removes thumbnails older than two days"""
def clean_thumbs_directory():
	now = time.time()
	for f in os.listdir(THUMBS_DIRECTORY):
		filename = os.path.join(THUMBS_DIRECTORY, f)
		last_edit = os.stat(filename).st_mtime
		if now - last_edit > 60*60*24*2:
			os.unlink(filename)

"""Download (and cache) <url> file to imgs/thumbs/. Returns saved file name. """
def download_img(url, file_name):
	print ('downloading ' + url)
	try:
		response = session.get(url, timeout=10)
		with open(file_name, "wb") as f:
			f.write(response.content)
	except Exception as e:
		print (e)
	return file_name
		
"""Resize an image (rewriting it)"""
def thumbnail(file_name, x=100, y=100):
    """Create a thumbnail of an image"""
    thumb_name = os.path.join(THUMBS_DIRECTORY, hashlib.md5(file_name.encode('utf-8')).hexdigest() + ".jpeg")
    if not os.path.exists(thumb_name):
        print("thumbnailing " + file_name)
        try:
            image = Image.open(file_name)
            # Replace ANTIALIAS with Resampling.LANCZOS
            image.thumbnail((x, y), Image.Resampling.LANCZOS)  # Modern replacement for ANTIALIAS
            image.save(thumb_name, "JPEG")
        except Exception as e:
            print(f"Error creating thumbnail for {file_name}: {str(e)}")
            return None
    return thumb_name
	
"""Download ad resize an img from a given URL"""
def download_and_thumbnail(url, x=120, y=100, directory=THUMBS_DIRECTORY):
	format = url.rsplit('.', 1)[1]		# www.site.com/path/img.jpg -> .jpg
	format = format.split('?', 1)[0] 	# could be: .jpg?w=100&y=200&...
	hashfun = hashlib.md5()
	hashfun.update(url.encode('utf-8'))
	file_name = os.path.join(directory, str(hashfun.hexdigest()) + '.' + format)
	if not os.path.exists(file_name):
		download_img(url, file_name)
		thumb_name = thumbnail(file_name, x=x, y=y)
		if thumb_name == None:
			return None
		thumb_name = thumb_name[len(DEPLOY_DIRECTORY):]	# cut off starting 'docs/'
		return thumb_name
	thumb_name = file_name[len(DEPLOY_DIRECTORY):]	# cut off starting 'docs/'
	return thumb_name

def download_feed(url, file_name):
    os.makedirs('feeds', exist_ok=True)
    content = None
    if FORCE_CACHE:
        response = session.get(url)
        content = response.text
        print("using cache")
    else:
        try:
            print("downloading " + url)
            response = session.get(url, timeout=10)
            content = response.text
        except requests.exceptions.RequestException:
            return None
            
    file_name = os.path.join("feeds", file_name)
    with open(file_name, "w") as f:
        f.write(content)
    return file_name

def get_feed(url, file_name):
	if DEBUG:
		file_name = 'feeds/'+file_name
	else:
		#try:
		file_name = download_feed(url, file_name)
		#except Exception, e:
		#	print e
		#	return []
	rss = feedparser.parse(file_name)
	return rss.entries

"""If the link is an image, puts a thumbnail of the picture inside the description"""	
def description_thumbs(entries):
	for entry in entries:
		if entry.link.endswith('.jpg') or entry.link.endswith('.jpeg') or entry.link.endswith('.png'):
			thumb = download_and_thumbnail(entry.link, x=200, y=200)
			if thumb != None:
				entry.description = '<img src=\''+ thumb +'\'><br/>' + entry.description
		elif entry.link.startswith('http://imgur.com/'):
			# TODO: add .gif support 
			#if entry.link.endswith('.jpg') or entry.link.endswith('.png'):
			if not entry.link.endswith('.gif'):
				print (entry.link)
				thumb = download_and_thumbnail(entry.link+'.jpg')
				if thumb != None:
					entry.description = '<img src=\''+ thumb +'\'><br/>' + entry.description
	return entries
	
def images_from_html(html):
	soup = BeautifulSoup(html, features="lxml")	
	tags = soup.find_all('img')
#	for img in images_from_html():
#		print img['src']
	return tags
	
def links_from_html(html):
	# TODO: Use regex here please
	soup = BeautifulSoup(html, features="lxml")
	tags = soup.find_all('a')
	return tags

def remove_html_tags(data):
    p = re.compile(r'<.*?>')
    return p.sub('', data)
def get_hackernews_feed():
	entries = get_feed("http://news.ycombinator.com/rss", "hackernews")
	for entry in entries:
		entry.comments_link = entry.comments
	return entries


def get_engadget_feed():
	entries = get_feed('http://www.engadget.com/rss.xml', 'engadget')
	
	for entry in entries:
		addr = None
		imgs = images_from_html(entry.description)
		for img in imgs:
			addr = img['src']
			if addr != None:
				break
		if addr == None: 
			continue
		thumb = download_and_thumbnail(addr)
		entry.description = remove_html_tags(entry.description)
		entry['img'] = thumb
	return entries
	
def get_reddit_description(entry, comment_page):
	print ("download/parse ", comment_page)
	try:
		response = session.get(comment_page, timeout=DOWNLOAD_TIMEOUT)
		html = response.text
		soup = BeautifulSoup(html, features="lxml")
		# we only parse a piece of the page, it could be very long because of comments:
		if len(soup) > 24000:
			soup = soup[0:23999] 
		
		# <form class="form-t3_ak2b8igo"><div>...
		#form = soup.find('form', {'id': 'form-t3_ak2b8igo'})
		mds = soup.find_all('div', {'class': 'md'})
		try: 
			entry.description = cut_description(mds[2])
			return True
		except IndexError as detail:
			print ('index error ', detail)
			return False
	except (UnicodeEncodeError, requests.exceptions.RequestException):
		return False
	
def get_reddit_like_feed(url, name, find_description=True):
	entries = get_feed(url, name)
	for entry in entries:
		entry.title = saxutils.escape(entry.title)
		entry.comments_link = entry.link
		
		# Handle different RSS feed structures
		entry_content = ''
		if hasattr(entry, 'summary_detail'):
			entry_content = entry.summary_detail.value
		elif hasattr(entry, 'summary'):
			entry_content = entry.summary
		elif hasattr(entry, 'content'):
			entry_content = entry.content[0].value
			
		tags = links_from_html(entry_content)
		
		found = False
		for tag in tags:
			# Update Reddit domain check
			if not tag['href'].startswith(("http://www.reddit.com/", "https://www.reddit.com/")):
				entry.link = tag['href']
				entry.description = ''
				found = True
				break
				
		if find_description and not found and not DEBUG:
			if not get_reddit_description(entry, entry.link):
				entry.description = ''
	return entries

def get_reddit_feed():
	return get_reddit_like_feed("http://www.reddit.com/.rss", "reddit")

def get_proggit_feed():
	return get_reddit_like_feed("http://www.reddit.com/r/programming/.rss", "proggit")
	
def get_reddit_videos():
	feeds = []
	feeds.append(get_reddit_like_feed('http://www.reddit.com/r/geek/.rss', 'r_geek', find_description=False))
	feeds.append(get_reddit_like_feed('http://www.reddit.com/r/technology/.rss', 'r_technology', False))
	feeds.append(get_reddit_like_feed('http://www.reddit.com/r/science/.rss', 'r_science', False))
	feeds.append(get_reddit_like_feed('http://www.reddit.com/r/scifi/.rss', 'r_scifi', False))
	feeds.append(get_reddit_like_feed('http://www.reddit.com/r/gaming/.rss', 'r_gaming', False))
	
	videos = []
	for feed in feeds:
		for entry in feed:
			if entry.link.startswith('http://www.youtube.com/watch?v='):
				# extract code from http://www.youtube.com/watch?v=3yaY98GTCYM#t=3m45s
				youtube_code = entry.link.split('http://www.youtube.com/watch?v=')[1]
				youtube_code = youtube_code.split('#')[0].split('&')[0]
				entry['thumb'] = 'http://i2.ytimg.com/vi/' + youtube_code + '/default.jpg'
				entry.title = cut_title(entry.title)
				videos.append(entry)
	return videos
	
def get_slashdot_feed():
	entries = get_feed("http://rss.slashdot.org/Slashdot/slashdot", "slashdot");
	for entry in entries:
		entry.description = remove_html_tags(entry.description) 
	return entries	


def main():
    # Create the docs directory
    if os.path.exists(DEPLOY_DIRECTORY):
        shutil.rmtree(DEPLOY_DIRECTORY)
    os.makedirs(os.path.join(DEPLOY_DIRECTORY, 'imgs', 'thumbs'))

    # Create .nojekyll file to prevent Jekyll from building the site
    with open(os.path.join(DEPLOY_DIRECTORY, '.nojekyll'), 'w') as f:
        pass

    # Download feeds and collect all entries
    clean_thumbs_directory()
    all_entries = []

    # Helper to add source and process entries
    def add_entries(entries_list, source_name):
        for entry in entries_list:
            entry.source_name = source_name
            # Attempt to get score/comment count, default to 0
            entry.score = 0
            entry.comments_count = 0

            # Heuristics for Hacker News
            if source_name == 'Hacker News':
                if hasattr(entry, 'points'): # Some hnrss feeds use 'points'
                    entry.score = int(entry.points)
                elif hasattr(entry, 'hn_points'): # Other hnrss feeds use 'hn_points'
                    entry.score = int(entry.hn_points)

                if hasattr(entry, 'hn_comments'): # Check for 'hn_comments' first
                    entry.comments_count = int(entry.hn_comments)
                elif hasattr(entry, 'num_comments'): # Check for 'num_comments'
                    entry.comments_count = int(entry.num_comments)
                elif hasattr(entry, 'comments'): # Fallback for 'comments'
                    try:
                        entry.comments_count = int(entry.comments)
                    except (ValueError, TypeError):
                        # This happens when entry.comments is a URL, which is expected for some feeds.
                        # In this case, we just leave comments_count as 0.
                        pass
            # Add more specific parsing for Reddit if needed, currently not directly available in standard RSS
            
            all_entries.append(entry)

    add_entries(get_hackernews_feed(), 'Hacker News')
    add_entries(description_thumbs(get_reddit_feed()), 'Reddit')
    add_entries(get_proggit_feed(), 'Proggit')
    add_entries(get_feed("http://www.dzone.com/links/feed/frontpage/rss.xml", "dzone"), 'DZone')
    add_entries(get_slashdot_feed(), 'Slashdot')
    add_entries(get_feed("http://www.techmeme.com/index.xml", "techmeme"), 'Techmeme')
    add_entries(get_feed("http://feeds.wired.com/wired/index", "wired"), 'Wired')
    add_entries(get_reddit_videos(), 'Videos')

    # Calculate score for each entry
    def calculate_custom_score(entry):
        # Recency: higher for newer articles. time.mktime gives seconds since epoch.
        # Max score for very new articles, decaying over time.
        published_timestamp = time.mktime(entry.published_parsed) if hasattr(entry, 'published_parsed') else datetime.now().timestamp()
        time_since_publish = datetime.now().timestamp() - published_timestamp
        
        # Simple decay: score decreases by 1 for every hour past. Adjust divisor for faster/slower decay.
        recency_score = max(0, 1000 - (time_since_publish / 3600)) 

        # Popularity: sum of score and comments (if available)
        popularity_score = getattr(entry, 'score', 0) + getattr(entry, 'comments_count', 0)

        # Combine recency and popularity (weights can be adjusted)
        # Prioritize recency slightly more for a fresh feed
        score = (recency_score * 0.7) + (popularity_score * 0.3)

        # Boost score for preferred sources
        if entry.source_name in ['Hacker News', 'Reddit', 'Proggit']:
            score *= 1.5  # 50% score boost

        return score

    for entry in all_entries:
        entry.custom_score = calculate_custom_score(entry)
    
    # Sort all entries by custom score
    all_entries.sort(key=lambda entry: entry.custom_score, reverse=True)

    # Create context dictionary for Flask template
    current_datetime_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    context = {
        'all_entries': all_entries,
        'current_datetime': current_datetime_str,
        'title': 'README'
    }

    # Render template and save to index.html
    app = Flask(__name__)
    with app.app_context():
        rendered_html = render_template('dashboard.html', **context)

    # Save the rendered HTML to the deployment directory
    output_path = os.path.join(DEPLOY_DIRECTORY, 'index.html')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(rendered_html)


if __name__ == "__main__":
    main()