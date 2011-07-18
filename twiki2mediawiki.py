#! /usr/bin/python

# Copyright 2011 Tom Parker
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import rcslib
import os
import subprocess
import MySQLdb
import random
import re
import datetime
import hashlib
import shutil

import local

con = MySQLdb.connect(host=local.mysqlHost, user=local.mysqlUser, passwd=local.mysqlPasswd, db=local.mysqlDb, init_command='SET NAMES utf8')

def camelCaseToMediawiki(s):
	s = s.translate(None, " ")
	result = local.nameMapping.get(s)
	if (result != None):
		return result
	result = ""
	lastIsUpper = True
	for c in s:
		if (c.isupper() and not lastIsUpper):
				result = result + "_" + c
		else:
			result = result + c
		lastIsUpper = c.isupper() or c == "#"
	return result

def camelCaseToMediawikiLink(s):
	result = camelCaseToMediawiki(s)
	if (result.find("_") != -1):
		result = result.replace("_", " ")
	return result

def splitMeta(s):
	meta = ""
	text = ""
	for l in s.splitlines(True):
		if (l.startswith("%META:")):
			meta = meta + l
		else:
			text = text + l
	return (meta, text)

def parseMeta(s):
	result = {"FILEATTACHMENT" : []}
	for l in s.splitlines():
		l = l[6:]
		parts = l.split("{")
		metaName = parts[0]
		values = parts[1][0:-2]
		if (metaName == "FILEATTACHMENT"):
			match = re.match('name="(.*?)".*comment="(.*?)".*date="(.*?)".*size="(.*?)"', values)
			name = match.group(1)
			comment = match.group(2)
			date = datetime.datetime.fromtimestamp(int(match.group(3)))
			size = match.group(4)
			result["FILEATTACHMENT"].append({"name" : name, "comment" : comment, "date" : date, "size" :size})
		else:
			result[metaName] = values
	return result

def parseTopicInfo(s):
	match = re.match('author="(.*?)".*date="(.*?)"', s)
	return (match.group(1), datetime.datetime.fromtimestamp(int(match.group(2))))

def processText(s, attachUrl):
	result = s
	result = re.sub('%INCLUDE{"(.*?)"}%', '{{:\\1}}', result)
	def linkReplacer(match):
		dest = match.group(1)
		if (dest.startswith('%ATTACHURL%')):
			return "[[%s]]" % (dest)
		if (dest.startswith('http://')):
			return dest
		return "[[%s]]" % (camelCaseToMediawikiLink(dest))
	result = re.sub('\\[\\[([^\\]]*)\\]\\]', linkReplacer, result)
	def linkReplacer(match):
		if (match.group(1).find("/") == -1):
			destination = camelCaseToMediawikiLink(match.group(1))
		else:
			destination = match.group(1)
		if (match.group(1) == match.group(2)):
			return "[[%s]]" % (destination)
		result = "[[%s|%s]]" % (destination, match.group(2))
		return result
	result = re.sub('\\[\\[([^\\[\\[]*?)\\]\\[(.*?)\\]\\]', linkReplacer, result)
	result = re.sub('%IMAGE{"(.*?)" .*caption="(.*?)"}.*%', '[[Image:\\1|thumb|\\2]]', result)
	result = re.sub('<img.*src="%ATTACHURLPATH%/(.*?)" alt="(.*?)".*/>', '[[Image:\\1|\\2]]', result)
	result = re.sub('<img.*src="' + attachUrl + '/(.*?)" alt="(.*?)".*/>', '[[Image:\\1|\\2]]', result)
	result = re.sub('<img.*alt="(.*?)" src="%ATTACHURLPATH%/(.*?)".*/>', '[[Image:\\2|\\1]]', result)
	result = re.sub('<img.*alt="(.*?)" src="' + attachUrl + '/(.*?)".*/>', '[[Image:\\2|\\1]]', result)
	result = re.sub('%Y%', '[[File:tick.gif|link=]]', result)
	result = re.sub('%ICON{wip}%', '[[File:wip.gif|link=]]', result)
	result = re.sub('\\[\\[\\%ATTACHURL\\%/', '[[File:', result)
	result = re.sub('%ATTACHURL%/', 'Image:', result)
	return result

def copyAttachments(topic, attachments):
	for attachment in attachments:
		dateString = attachment["date"].strftime("%Y%m%d%H%M%S")
		m = hashlib.md5()
		m.update(attachment["name"]);
		md5 = m.hexdigest()
		a = md5[0:1]
		b = md5[0:2]
		twikiFile = local.twikiAttachDir + "/" + topic + "/" + attachment["name"]
		mediawikiDir = local.mediawikiImageDir + "/" + a + "/" + b
		mediawikiFile = mediawikiDir + "/" + attachment["name"]
		if (not os.path.exists(mediawikiDir)):
			os.makedirs(mediawikiDir)
		shutil.copyfile(twikiFile, mediawikiFile)
		c.execute("insert into image (img_name, img_description, img_metadata, img_timestamp, img_sha1, img_size) values (%s, %s, 0, %s, 0, %s)", (attachment["name"], attachment["comment"], dateString, attachment["size"]))

c = con.cursor()

c.execute("SET NAMES utf8")
c.execute("SET CHARACTER SET utf8")
c.execute("SET character_set_connection=utf8")

if (local.deleteEverything and local.yesReallyDeleteEverything):
	c.execute("delete from page")
	c.execute("delete from text")
	c.execute("delete from revision")
	c.execute("delete from image")

con.commit()

r = rcslib.RCS()
for f in r.listfiles():
	if (f.startswith("Web") and not f.startswith("WebHome")):
		continue
	#if (not f.startswith("WebHome")):
	#	continue
	twikiName = f.split(".")[0]
	title = camelCaseToMediawiki(twikiName)
	i = r.info(f)
	total = int(i['total revisions'])
	print "%s %s %d" % (f, title, total)
	c.execute("insert into page (page_namespace, page_title, page_restrictions, page_random, page_latest, page_len) values (0, %s, '', %s, 0, 0)", (title, random.random()));
	page_id = c.lastrowid
	parent_id = 0
	length = 0
	date = 0
	metaText = None
	for rev in range(1, total + 1):
		revStr = "-r1." + str(rev)
		r.checkout(f, otherflags=revStr)
		p = subprocess.Popen(("../fromtwiki.pl", f), stdout=subprocess.PIPE)
		rawText = p.communicate()[0]
		metaText, text = splitMeta(rawText)
		attachUrl = "/twiki/pub/ElectricMini/" + twikiName
		text = processText(text, attachUrl)
		length = len(text)
		(twikiAuthor, date) = parseTopicInfo(parseMeta(metaText)["TOPICINFO"])
		dateString = date.strftime("%Y%m%d%H%M%S")
		if (local.skipAuthors.has_key(twikiAuthor)):
			continue
		(authorId, author) = local.authorMapping[twikiAuthor]
		c.execute("insert into text (old_text, old_flags) values (%s, 'utf-8')", (text));
		text_id = c.lastrowid
		c.execute("insert into revision (rev_page, rev_text_id, rev_user, rev_user_text, rev_timestamp, rev_len, rev_parent_id, rev_comment) values (%s, %s, %s, %s, %s, %s, %s, %s)", (page_id, text_id, authorId, author, dateString, length, parent_id, "Imported from TWiki by fromTwiki.py"))
		parent_id = c.lastrowid
	c.execute("update page set page_touched=%s, page_latest=%s, page_len=%s where page_id=%s", (dateString, parent_id, length, page_id))
	meta = parseMeta(metaText)
	copyAttachments(twikiName, meta["FILEATTACHMENT"])
	con.commit()
	#break;
