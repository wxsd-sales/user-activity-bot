import json
import tornado.web

class BaseHandler(tornado.web.RequestHandler):
    def get_current_user(self):
        cookie = self.get_secure_cookie("UserActivitySessionId", max_age_days=1, min_version=1)
        if cookie != None:
            cookie = cookie.decode('utf-8')
            cookie = json.loads(cookie)
            if self.application.settings['db'].is_user(cookie['id']):
                self.application.settings['db'].update_expire_date(cookie['id'])
            else:
                cookie = None
        return cookie

    def set_current_user(self, access_token, person):
        my_cookie = {"token":access_token, "id":person['id'], "emails":person.get('emails')}
        print("set_current_user cookie:{0}".format(my_cookie))
        self.set_secure_cookie("UserActivitySessionId", json.dumps(my_cookie), expires_days=1, version=1)
        self.application.settings['db'].insert_user(person['id'], access_token)