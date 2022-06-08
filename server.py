# -*- coding: utf-8 -*-
#!/usr/bin/env python
from inspect import trace
import json
import os
import pytz
import traceback

from lib.mongo_db_controller import UserDB

import tornado.gen
import tornado.httpserver
import tornado.ioloop
import tornado.web

from common.spark import Spark

from lib.mongo_db_controller import UserDB
from lib.settings import Settings
from handlers.base import BaseHandler
from handlers.oauth import OAuthHandler

from datetime import datetime
from dateutil import parser
from tornado.options import define, options, parse_command_line
from tornado.httpclient import AsyncHTTPClient, HTTPRequest, HTTPError
from threading import Thread

define("debug", default=False, help="run in debug mode")
class ActiveThreads(object):
    threads = {}

class MainHandler(BaseHandler):
    @tornado.web.asynchronous
    @tornado.gen.coroutine
    def get(self):
        try:
            person = self.get_current_user()
            print("MainHandler person:{0}".format(person))
            if not person:
                self.redirect('/oauth')
            else:
                self.render("main.html")
        except Exception as e:
            traceback.print_exc()

    @tornado.web.asynchronous
    @tornado.gen.coroutine
    def post(self):
        try:
            secret_equal = Spark.compare_secret(self.request.body, self.request.headers.get('X-Spark-Signature'), Settings.secret)
            if secret_equal or Settings.secret.lower()=="none":
                webhook = json.loads(self.request.body)
                if webhook['data']['personId'] != Settings.bot_id:
                    print("MainHandler Webhook Received:")
                    print(webhook)
                    message = yield self.application.settings['spark'].get_with_retries_v2('{0}/messages/{1}'.format(Settings.api_url, webhook['data']['id']))
                    command = message.body.get('text','').lower().strip()
                    print('command:{0}'.format(command))
                    #print(ActiveThreads.threads)
                    reply_msg = ""
                    if command.startswith('login'):
                        reply_msg = self.login_msg()
                    elif command.startswith('all') or command.startswith('inactive') or command.startswith('pending') or command.startswith('invitepending'):
                        user_t = ActiveThreads.threads.get(webhook['actorId'])
                        if user_t == None or not user_t['thread'].is_alive():
                            user_token = self.application.settings['db'].get_token(webhook['actorId'])
                            if user_token != None:
                                days_old = None
                                filter = "all"
                                if command.startswith('inactive'):
                                    filter = "inactive"
                                elif command.startswith('invitepending') or command.startswith('pending'):
                                    filter = "pending"
                                    precommand, postcommand = command.split('pending')
                                    try:
                                        days_old = int(postcommand)
                                    except Exception as e:
                                        reply_msg = '```pending``` command should be in the format ```pending N``` where ```N``` is the minimum number of days old an "unactivated" account must be in order to be included in the report. For example:  \n'
                                        reply_msg += '```pending 90```  \n'
                                        reply_msg += 'You provided:  \n'
                                        reply_msg += '```{0}```'.format(command)
                                if reply_msg == "":
                                    t = Thread(target=self.list_users, args=[user_token, webhook['actorId'], filter], kwargs={"days_old":days_old}, daemon=True)
                                    t.start()
                                    ActiveThreads.threads.update({webhook['actorId']: {"thread": t, "user_count":0}})
                                    reply_msg = "A user activity report is being generated and will be sent to you as a .csv attachment to you by this bot as soon as it's complete."
                            else:
                                reply_msg = "You are not logged in.  \n"
                                reply_msg += self.login_msg()
                        else:
                            reply_msg = "A user activity report is already being generated for you.  It has analyzed {0} users in your org so far.  ".format(user_t["user_count"])
                            reply_msg += "You must wait for this task to complete before you can generate another."
                    else:
                        reply_msg = self.help_msg()
                    yield self.application.settings['spark'].post_with_retries('{0}/messages'.format(Settings.api_url), {'markdown':reply_msg, 'roomId':webhook['data']['roomId']})
            else:
                print("MainHandler Secret does not match")
        except Exception as e:
            print("MainHandler General Error:{0}".format(e))
            traceback.print_exc()
    
    def login_msg(self):
        return "Click [this link to log in]({0}).".format(Settings.base_uri)

    def help_msg(self):
        msg = "The following commands are recognized by this bot:\n\n"
        msg += "**all** - "
        msg += "Returns a .csv file with the ```lastActivity``` of all users in your organization.\n\n"
        msg += "**inactive** - "
        msg += "Returns a .csv file with the ```lastActivity``` of users in your organization whose status is ```inactive``` or ```unknown```.\n\n"
        msg += "**pending** N - "
        msg += "Returns a .csv file of users in your organization whose ```invitePending``` state is ```true``` (never logged in) and whose accounts were created more than N days ago.\n\n"
        msg += "**login** - "
        msg += "Authenticates to this application.  Required in order to retrieve the activity status of users in your org.\n\n"
        #msg += "You can find a walkthrough for this demo, along with the code at: https://github.com/WXSD-Sales/APMBot  \n"
        msg += "If you have any questions or ideas for features you would like to see added, please reach out to wxsd@external.cisco.com"
        return msg


    def list_users(self, user_token, user_id, filter, days_old=None):
        try:
            url = '{0}/people?max=500'.format(Settings.api_url)
            filename = "{0}.csv".format(user_id)
            wrote_data = False
            if filter == "pending":
                print('days_old:{0}'.format(days_old))
                self.write_pending_headers(filename)
            else:
                self.write_headers(filename)
            while url != None:
                people = Spark(user_token).get_with_retries_std(url)
                UserDB.db.update_expire_date(user_id)
                items = people.body.get('items',[])
                if len(items) > 0:
                    if ActiveThreads.threads.get(user_id):
                        ActiveThreads.threads[user_id]["user_count"] += len(items)
                    wrote_data = True
                    self.write_users(filename, items, filter, days_old)
                url = people.headers.get('Link')
                if url != None:
                    extra, url = url.split("<")
                    url, extra = url.split(">")
                    url = url.strip()
                print("Next Url:{0}".format(url))
            if wrote_data:
                self.application.settings['spark'].upload(None, "UserActivity.csv", filename, 'text/csv', markdown='', personId=user_id)
            else:
                msg = "Unfortunately, no data could be generated because of an error or lack of access."
                self.application.settings['spark'].post_with_retries('{0}/messages'.format(Settings.api_url), {'markdown':msg, 'toPersonId':user_id})
            os.remove(filename)
        except Exception as e:
            traceback.print_exc()

    def write_headers(self, filename):
        with open(filename, 'w') as f:
            f.write('Email,LastActivity,Status\n')

    def write_pending_headers(self, filename):
        with open(filename, 'w') as f:
            f.write('Email,Created,Age (in Days),InvitePending\n')

    def write_users(self, filename, items, filter, days_old):
        now = datetime.now(pytz.utc)
        try:
            for item in items:
                item_email = item.get('emails', [None])[0]
                if filter == "all" or (filter == "inactive" and item.get('status') in ["inactive", "pending", "unknown"]):
                    self.write_user(filename, [item_email, str(item.get('lastActivity')), str(item.get('status'))])
                elif filter == "pending" and item.get('invitePending'):
                    try:
                        created_datetime = parser.isoparse(item.get('created'))
                        days_age = (now - created_datetime).days
                        if days_old in [None, 0] or days_age > days_old:
                            self.write_user(filename, [item_email, str(item.get('created')), str(days_age), str(item.get('invitePending'))])
                    except Exception as e:
                        traceback.print_exc()
        except Exception as e:
            traceback.print_exc()

    def write_user(self, filename, items):
        write_str = ",".join(items) + "\n"
        with open(filename, 'a') as f:
            f.write(write_str)

def manage():
    print("Managing Threads...")
    for user in list(ActiveThreads.threads.keys()):
        if not ActiveThreads.threads[user]['thread'].is_alive():
            print(ActiveThreads.threads[user]['thread'])
            ActiveThreads.threads[user]['thread'].join()
            ActiveThreads.threads.pop(user)
            print("Joined thread for {0}".format(user))


@tornado.gen.coroutine
def main():
    try:
        parse_command_line()
        static_dir = os.path.join(os.path.dirname(__file__), "static")
        app = tornado.web.Application(
            [   (r"/", MainHandler),
                (r"/oauth", OAuthHandler),
            ],
            cookie_secret="asdfuertennesseevalleyauthaxw1uej43a",
            xsrf_cookies=False,
            debug=options.debug,
            template_path=static_dir
            )
        app.settings['debug'] = options.debug
        app.settings['settings'] = Settings
        app.settings['spark'] = Spark(Settings.token)
        db = UserDB.db
        app.settings['db'] = db
        server = tornado.httpserver.HTTPServer(app)
        print("Serving... on port {0}".format(Settings.port))
        server.bind(Settings.port)  # port
        print("Debug: {0}".format(app.settings["debug"]))
        server.start()
        ioloop = tornado.ioloop.IOLoop.instance()
        thread_manager_task = tornado.ioloop.PeriodicCallback(
            manage,
            120 * 1000
        )
        thread_manager_task.start()
        ioloop.start()
        print('Done')
    except Exception as e:
        traceback.print_exc()

if __name__ == "__main__":
    main()
