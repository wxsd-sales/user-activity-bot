#!/usr/bin/env python
import json
import traceback
import urllib

import tornado.gen
import tornado.web

from tornado.httpclient import AsyncHTTPClient, HTTPRequest, HTTPError

from handlers.base import BaseHandler
from lib.settings import Settings

from common.spark import Spark

class OAuthHandler(BaseHandler):
    @tornado.web.asynchronous
    @tornado.gen.coroutine
    def get(self):
        try:
            code = self.get_argument("code",None)
            state = self.get_argument("state",None)
            next = self.get_argument("next",None)
            print("Code: {0}".format(code))
            print("State: {0}".format(state))
            print("Next: {0}".format(next))
            ret_val = {"success":False, "code":500, "message":"Unknown Error"}
            if code != None:
                ret_val = yield self.generate_token(code)
            else:
                #ret_val = {"success":False, "code":500, "message":"'code' cannot be null."}
                self.authorize()
                return
            if ret_val == None:
                return
            else:
                self.write(json.dumps(ret_val))
        except Exception as ex:
            traceback.print_exc()

    def authorize(self):
        print(self.request.headers)
        print(self.request.body)
        if not self.get_current_user():
            print("Not authenticated.")
            print(self.request.full_url())
            next = self.get_argument("next", None)
            state_url = "{0}://{1}/oauth?".format(self.request.protocol, self.request.host)
            if next is not None:
                state_url += "next={0}&".format(next)
            print("state_url:{0}".format(state_url))
            url = '{0}/authorize?client_id={1}'.format(Settings.api_url, Settings.client_id)
            url += '&response_type=code&redirect_uri={0}'.format(urllib.parse.quote(Settings.redirect_uri))
            url += '&scope=' + Settings.scopes
            url += '&state={0}'.format(urllib.parse.quote(state_url))
            print(url)
            self.redirect(url)
        else:
            print("Already authenticated.")
            print(self.request.full_url())
            print(self.get_argument("next", u"/"))
            self.redirect(self.get_argument("next", u"/"))

    @tornado.gen.coroutine
    def generate_token(self, code):
        url = "{0}/access_token".format(Settings.api_url)
        payload = "client_id={0}&".format(Settings.client_id)
        payload += "client_secret={0}&".format(Settings.client_secret)
        payload += "grant_type=authorization_code&"
        payload += "code={0}&".format(code)
        payload += "redirect_uri={0}".format(Settings.redirect_uri)
        headers = {
            'cache-control': "no-cache",
            'content-type': "application/x-www-form-urlencoded"
            }
        request = HTTPRequest(url, method="POST", headers=headers, body=payload)
        http_client = AsyncHTTPClient()
        try:
            response = yield http_client.fetch(request)
            resp = json.loads(response.body.decode("utf-8"))
            print("AuthHandler resp:{0}".format(resp))
            person = yield Spark(resp["access_token"]).get_with_retries_v2('{0}/people/me'.format(Settings.api_url))
            self.set_current_user(resp['access_token'], person.body)
            print("login success, redirecting to Main Page")
            self.redirect("/")
            return
        except HTTPError as he:
            print("AuthHandler HTTPError Code: {0}, {1}".format(he.code, he.message))
            raise tornado.gen.Return({"success":False, "code":he.code, "message":he.message})
        except Exception as e:
            traceback.print_exc()
            message = "{0}".format(e)
            raise tornado.gen.Return({"success":False, "code":500, "message":message})
