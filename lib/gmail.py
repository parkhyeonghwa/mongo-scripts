
import imaplib
import keyring
import getpass
import rfc822
import re
import datetime
import time
import pprint

import smtplib
from email.MIMEText import MIMEText
import email

import pymongo

class gmail:
    def __init__(self,emailaddr,pwd,mongo_host="127.0.0.1"):
        self.emailaddr = emailaddr
        self.pwd = pwd;

        #imap
        self.mailbox = imaplib.IMAP4_SSL( "imap.gmail.com" , 993 )
        self.mailbox.login( emailaddr , pwd )
        self.select( "INBOX" )
        
        #smtp
        self.smtp = smtplib.SMTP( "smtp.gmail.com", 587)
        self.smtp.ehlo()
        self.smtp.starttls()
        self.smtp.ehlo()
        self.smtp.login( emailaddr , pwd )

        #mongo
        self.mongo = pymongo.Connection( mongo_host )
        self.cache = self.mongo.gmail_cache_raw.cache
        
    def select(self,name):
        self.mailbox.select( name )
        self.folder = name

    def list(self):
        res = self.mailbox.uid( "search" , "ALL" )
        return res[1][0].split()


    def _cleanID(self,foo):
        foo = foo.lower();
        foo = foo.strip();
        
        if foo.count( "<" ) != 1 or foo.count( ">") != 1:
            if foo.count( " " ):
                raise Exception( "bad id [%s]" , foo )
            return foo
        
        foo = foo.partition( "<" )[2]
        foo = foo.partition( ">" )[0]
        
        return foo

    def _cleanSingleHeader(self,name,value):
        if name == "message-id":
            return self._cleanID( value )
        
        if name == "to":
            return [ z.strip() for z in value.split( "," ) ]

        if name == "references":
            return [ self._cleanID( x ) for x in re.split( "\s+" , value.lower() ) ]

        if name == "in-reply-to":
            return self._cleanID( value )
        
        if name == "date":
            t = rfc822.parsedate( value )
            return datetime.datetime.fromtimestamp( time.mktime( t ) )
        
        return value

    def _convert_raw( self, txt ):

        headers = {}
        
        prev = ""
        while True:
            line,end,txt = txt.partition( "\n" )
            line = line.replace( "\r" , "" )
            if len(line) == 0:
                break
            
            if line[0].isspace():
                prev += "\n" + line
                continue
            
            if len(prev) > 0:
                name,temp,value = prev.partition( ":" )

                name = name.lower()
                value = value.strip()
                
                value = self._cleanSingleHeader( name , value )

                if name in headers:
                    headers[name].append( value )
                else:
                    headers[name] = [ value ]
            prev = line
        
        for x in headers:
            if len(headers[x]) == 1:
                headers[x] = headers[x][0]
                
        return { "headers" : headers , "body" : txt }
    
    def fetch(self,uid):
        key = self.emailaddr + "-" + self.folder + "-" + str(uid)
        
        raw = self.cache.find_one( { "_id" : key } )
        if raw:
            return self._convert_raw( raw["data"] )

        typ, data = self.mailbox.uid( "fetch" , uid, '(RFC822)')
        if typ != "OK":
            raise Exception( "failed loading uid: %s typ: %s" % ( str(uid) , str(typ) ) )
        data = data[0][1]

        self.cache.insert( { "_id" : key , "data" : data } )
        return self._convert_raw( data )


    def send_simple(self,to,subject,body,replyto=None):
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['To']      = to
        if replyto != None:
            msg["Reply-To"] = replyto
        self.smtp.sendmail( "eliot@10gen.com", to , msg.as_string() )