#!/usr/bin/python
# -*- coding: utf-8 -*-

import urllib, urllib2, cookielib, re, os, time
import cPickle as pickle
from datetime import datetime, timedelta


class TSMS:
    def __init__(self, debug_log = False, path = ''):
        self.url = 'http://tsms'
        self.login_url = 'http://tsms/login/'
        self.username = 'swang2'
        self.password = '123456'
        path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tsms')
        self.cookie_file = os.path.join(path, 'cookie.txt')
        self.station_info_file = os.path.join(path, 'station_info.txt')
        self.set_debug_log(debug_log)
        self.init_station_info()

    def init_station_info(self):
        self.used_column = [1,2,5,6,7,8,10,11,12,19,20,21]
        self.info_column = ['restrict', 'name', 'product', 'pc_ip', 'tm500_ip', 'pxi', 'product_2', 'hardware', 'umbra', 'available', 'username', 'password']
        assert len(self.used_column) == len(self.info_column), 'length not match for used_column and info_column.'
        self.info_index = {}
        for i, info in enumerate(self.info_column):
            self.info_index[info] = i
        self.station_info = None

    def set_debug_log(self, debug_log):
        self.debug_log = debug_log

    def print_(self, msg):
        print msg

    def debug_print(self, msg):
        if self.debug_log: self.print_(msg)

    def print_cookie(self, c):
        for index, cookie in enumerate(c):
            self.print_('cookie[%d]%s' % (index, str(cookie)))

    def login_and_save_cookie(self):
        self.debug_print('getting login page...')
        cookie = cookielib.MozillaCookieJar(self.cookie_file)
        handler = urllib2.HTTPCookieProcessor(cookie)
        opener = urllib2.build_opener(handler)
        response = opener.open(self.url)
        data = response.read()
        #<input type=\'hidden\' name=\'csrfmiddlewaretoken\' value=\'Iv2B8xdW09qzkq0GBOmQY1z5WvQxTcWf\' />\n
        r = re.search("<input\s+type='hidden'\s+name='csrfmiddlewaretoken'\s+value='(\w+)'\s*/>", data)
        if not r: raise Exception('cannot find token from login page')
        token = r.group(1)
        self.debug_print('trying to login...')
        post_data = urllib.urlencode({'username' : self.username,
                                      'password' : self.password,
                                      'csrfmiddlewaretoken' : token,
                                      'remember_me':'on'})
        rsp = opener.open(self.login_url, post_data)
        cookie.save(ignore_discard = True, ignore_expires = True)
        if self._is_login_page(rsp.read()):
            raise Exception('cannot login to TSMS')
        self.debug_print('login ok and cookie saved.')

    def install_opener_with_cookie(self):
        cookie = cookielib.MozillaCookieJar()
        cookie.load(self.cookie_file, ignore_discard=True, ignore_expires=True)
        token = [c.value for c in cookie if c.name == 'csrftoken']
        assert len(token) == 1, 'invalid token: %s' % str(token)
        #urllib2build_openeropener
        opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cookie))
        urllib2.install_opener(opener)
        self.debug_print('loaded cookie.')
        return token[0]

    def _is_login_page(self, data):
        return True if data.find('Login to Aeroflex') >= 0 else False

    def get_page_with_cookie(self, url = '', post_data_dict = None, timeout = 30):
        token = self.install_opener_with_cookie()
        if not post_data_dict is None:
            assert isinstance(post_data_dict, dict), 'invalid post_data_dict: %s' % str(post_data_dict)
            post_data_dict['csrfmiddlewaretoken'] = token
        post_data = urllib.urlencode(post_data_dict) if post_data_dict else None
        if post_data: self.debug_print('Post Data: %s' % post_data)
        try:
            start_time = time.time()
            rsp = urllib2.urlopen(url, data = post_data, timeout = timeout)
            elapse_time = time.time() - start_time
        except Exception as e:
            self.print_(e)
            return ''
        data = rsp.read()
        if data and not self._is_login_page(data):
            self.debug_print('get page "%s" ok after %.1fs.' % (url, elapse_time))
            return data
        return ''

    def get_page(self, url = '', post_data_dict = None, timeout = 30):
        url = url or self.url
        if os.path.isfile(self.cookie_file):
            data = self.get_page_with_cookie(url, post_data_dict = post_data_dict, timeout = timeout)
            if data: return data
        self.login_and_save_cookie()
        data = self.get_page_with_cookie(url, post_data_dict = post_data_dict, timeout = timeout)
        if data: return data
        self.debug_print('get page "%s" error.' % url)
        return ''

    def get_station_info_page(self):
        url = 'http://tsms/calander=%s/' % datetime.now().strftime('%Y-%m-%d')
        post_data_dict = {'update_stations_button_set' : 'Test Station info.'}
        return self.get_page(url, post_data_dict = post_data_dict)

    def book(self, machine, start_datetime, end_datetime, contents = 'cue debug test'):
        url = 'http://tsms/book=0/'
        start_year, start_month, start_day, start_time = start_datetime.strftime('%Y-%m-%d-%H:%M').split('-')
        end_year, end_month, end_day, end_time = end_datetime.strftime('%Y-%m-%d-%H:%M').split('-')
        post_data_dict = {'subject': contents,
                          'Select_Test_Station': machine.upper(),
                          'start_month': start_month,
                          'start_day': start_day,
                          'start_year': start_year,
                          'start_time': start_time,
                          'end_month': end_month,
                          'end_day': end_day,
                          'end_year': end_year,
                          'end_time': end_time,
                          'book_event_button': 'Book Calander event'
                         }
        page_data = self.get_page(url, post_data_dict = post_data_dict)
        #open(r'P:\AAS_TM500_LTE\User_Working_Folders\WangShouliang\tools\temp\debug1.txt', 'w').write(page_data)
        #page_data = open(r'P:\AAS_TM500_LTE\User_Working_Folders\WangShouliang\tools\temp\debug1.txt', 'r').read()
        record = self.get_my_booking(page_data)
        return record

    def delete(self, book_number, machine, start_datetime, end_datetime, contents = 'cue debug test'):
        url = 'http://tsms/book=%s/' % book_number
        start_year, start_month, start_day, start_time = start_datetime.strftime('%Y-%m-%d-%H:%M').split('-')
        end_year, end_month, end_day, end_time = end_datetime.strftime('%Y-%m-%d-%H:%M').split('-')
        post_data_dict = {'subject': contents,
                          'Select_Test_Station': machine.upper(),
                          'start_month': start_month,
                          'start_day': start_day,
                          'start_year': start_year,
                          'start_time': start_time,
                          'end_month': end_month,
                          'end_day': end_day,
                          'end_year': end_year,
                          'end_time': end_time,
                          'delete_event_button': 'Delete Calander event'
                         }
        page_data = self.get_page(url, post_data_dict = post_data_dict)
        record = self.get_my_booking(page_data)
        return record

    def datetime_to_floattime(self, t):
        return int(2*(t.hour + t.minute/60.0))/2.0  # floor

    def floattime_to_datetime(self, t):
        n = datetime.now()
        return datetime(n.year, n.month, n.day, hour = int(t), minute = int((t - int(t))*60))

    def get_my_booking(self, page_data = ''):
        if not page_data:
            url = 'http://tsms/calander=%s/' % datetime.now().strftime('%Y-%m-%d')
            page_data = self.get_page(url)
            if not page_data: return []
        r = re.search(r'My Bookings(?:<[^>]+>)+(\d+)<(.*?)</table>', page_data)
        if r:
            n, content = int(r.group(1)), r.group(2)
            if n < 1 or n > 5: raise Exception('invalid booking numbers %d detected. should in 1~5.' % n)
            records = []
            for r in re.finditer(r'add_event=([\d:]+)=([\d\-]+)=(\w+)/">(\d+)</a>\s*\3(?:<[^>]+>)+\1(?:<[^>]+>)+([\d:]+)<', content):
                # add_event=03:00=2015-10-15=PFC06, 29694, 6:46:15
                start_time, start_date, machine, book_id, duration = [r.group(i) for i in [1,2,3,4,5]]
                hour, minute = map(int, start_time.split(':'))
                start_datetime = datetime(*tuple(map(int, start_date.split('-'))), hour = hour, minute = minute)
                hour, minute, second = map(int, duration.split(':'))
                end_datetime = start_datetime + timedelta(hours = hour, minutes = minute, seconds = second)
                records.append((book_id, machine, self.datetime_to_floattime(start_datetime), self.datetime_to_floattime(end_datetime)))
            if len(records) != n: raise Exception('find %d records. should be %d. Content: %s' % (len(records), n, content))
            return records
        else:
            self.debug_print('No any booking currently.')
            return []

    def save_current_page(self, filename):
        url = 'http://tsms/calander=%s/' % datetime.now().strftime('%Y-%m-%d')
        data = self.get_page(url)
        if not data:
            self.debug_print('No data from the page.')
            return
        open(filename, 'w').write(data)

    def get_current_page(self, filename = ''):
        if filename:
            if not os.path.isfile(filename): raise Exception('no file found, %s!' % filename)
            return open(filename, 'r').read()
        url = 'http://tsms/calander=%s/' % datetime.now().strftime('%Y-%m-%d')
        data = self.get_page(url)
        if not data:
            self.debug_print('No data from the page.')
            return ''
        return data

    def get_current_booking(self, filename = ''):
        data = self.get_current_page(filename)
        if not data: return None
        r = re.search(r'<table id="day_table" >([\w\W]*)</table>', data)
        if not r: raise Exception('Error: table data not found in page!')
        table_data = r.group(1)
        table_rows = re.findall(r'<tr>[\w\W]+?</tr>', table_data)
        # table_rows[0]: head, table_rows[1]: foot
        head_data = re.findall(r'(?<=>)[\w\s]+?(?=</th>)', table_rows[0])
        time_slot, machines = head_data[0], head_data[1:]
        if time_slot != 'Time Slot': raise Exception('Error: invalid table head. %s' % head_data)
        time_list = []
        machine_dict = {}
        for m in machines:
            machine_dict[m] = []
        for row in table_rows[2:]:
            for i, td in enumerate(re.findall(r'<td[\w\W]+?</td>', row)):
                r = re.search(r'<td[^>]+class="(\w+)"', td)
                if not r: raise Exception('Error: no class found in td. %s' % td)
                td_class = r.group(1)
                r = re.search(r'<img src="(/\w+)*/([\w.]+)"', td)
                td_img = r.group(2) if r else None
                r = re.search(r'>([\r\n]+)?\s*([^<\s]+)<', td)
                td_text = r.group(2) if r else None
                if td_class == 'SectionHeaderStyle':
                    assert i == 0, 'invalid td class, %s' % td_class
                    td_output = td_text
                elif td_class == 'BgcolorAutomationRunSlot':
                    assert td_img == 'process.ico', 'invalid td img, %s' % td_img
                    td_output = td_text
                elif td_class == 'BgcolorFreeSlot':
                    if td_img == 'user_male_add.ico':
                        td_output = 'Free'
                    elif td_img == 'dialog_warning.png':
                        td_output = 'NA'
                    elif td_img is None:
                        td_output = 'Past'
                    else:
                        raise Exception('invalid td img, %s' % td_img)
                elif td_class == 'BgcolorBookedSlot':
                    td_output = '[%s]' % td_text
                else:
                    raise Exception('invalid td class, %s' % td_class)
                if i == 0:
                    time_list.append(td_output)
                else:
                    machine_dict[machines[i-1]].append(td_output)
        time_tuple = zip(time_list, [i for i in range(len(time_list))])
        time_tuple.sort()
        sort_list = [t[1] for t in time_tuple]
        time_list = [t[0] for t in time_tuple]
        for k, v in machine_dict.items():
            if not self._filter_machine(k):
                del machine_dict[k]
            else:
                machine_dict[k] = [v[i] for i in sort_list]
        machines = filter(self._filter_machine, machines)
        if len(machines) != len(machine_dict): raise Exception('length not match. machines %d != dict %d' % (len(machines), len(machine_dict)))
        return time_list, machine_dict

    def parse_station_info(self, data):
        tr_list = re.findall(r'(?:<tr>|</tfoot>).*?</tr>', data)  # the first line lack of <tr>
        #tr_list = re.findall(r'<tr>.*?</tr>', data)  # the first line lack of <tr>
        assert len(tr_list) > 2, 'invalid station info, len(tr_list) is %d' % len(tr_list)
        info = []
        td_list_len = None
        for tr in tr_list[1:]:
            temp_td_list = re.findall(r'<td[^>]*>.*?</td>', tr)
            temp_td_list = [td for i, td in enumerate(temp_td_list) if i in self.used_column]
            td_list = []
            for s in temp_td_list:
                content = s[s.find('>')+1:s.find('</td>')].replace('<br>', ' ')
                content = ' '.join(re.findall(r'(?:^|(?<=>))[^<]*(?:(?=<)|$)', content))
                td_list.append(content)
            assert td_list_len is None or td_list_len == len(td_list), 'invalid td numbers: %d, header %d' % (len(td_list), td_list_len)
            td_list_len = len(td_list)
            info.append(td_list)
        return info

    def load_station_info(self):
        assert os.path.isfile(self.station_info_file), 'file %s not found!' % self.station_info_file
        return pickle.load(open(self.station_info_file, 'rb'))

    def save_station_info(self, station_info):
        assert station_info, 'no valid station info to save'
        pickle.dump(station_info, open(self.station_info_file, 'wb'))

    def reload_station_info(self):
        data = self.get_station_info_page()
        #data = open('5.txt', 'r').read()
        info = self.parse_station_info(data)
        self.station_info = info
        self.save_station_info(info)

    def get_station_info(self):
        # return [[info1, info2, ...], [info1, info2, ...], ...]
        if self.station_info:
            return self.station_info
        elif os.path.isfile(self.station_info_file):
            self.station_info = self.load_station_info()
            return self.station_info
        else:
            self.reload_station_info()
            return self.station_info

    def get_all_stations(self):
        return [info[self.info_index['name']] for info in self.get_station_info() if self._filter_machine(info[self.info_index['name']])]

    def _filter_machine(self, name):
        return re.search('^(rav|pfc)', name, flags = re.IGNORECASE)

    def _extract_record(self, column, value):
        assert column in self.info_index, 'invalid column : %s' % column
        for info in self.get_station_info():
            index = self.info_index[column]
            if info[index].lower().strip() == value.lower().strip():
                return info
        return []

    def find_machine_record(self, machine_name_or_ip):
        if re.search(r'^(\d+\.){3}\d+$', machine_name_or_ip):  # ip address
            record = self._extract_record('pc_ip', machine_name_or_ip) or self._extract_record('tm500_ip', machine_name_or_ip)
            if not record: self.print_('no record found for ip %s' % machine_name_or_ip)
        else:
            record = self._extract_record('name', machine_name_or_ip)
            m = ''
            if not record:
                r = re.search(r'^(\w{3})0(\d)$', machine_name_or_ip)
                if r:
                    m = '%s%s' % (r.group(1), r.group(2))
                    record = self._extract_record('name', m)
            if not record: self.print_('no record found for %s(or %s)' % (machine_name_or_ip, m))
        if record: record = dict(zip(self.info_column, record))
        return record

    def name_to_ip(self, machine_name):
        record = self.find_machine_record(machine_name)
        return record['pc_ip'] if record else ''

    def ip_to_name(self, ip):
        record = self.find_machine_record(ip)
        return record['name'] if record else ''


if __name__ == '__main__':
    tsms = TSMS(debug_log = True)
    #data = tsms.get_page()
    #open('3.txt','w').write(data)
    #data = tsms.get_station_info_page()
    #open('5.txt','w').write(data)
    #data = open('5.txt', 'r').read()
    #data = tsms.parse_station_info(data)
    import pprint
    #pprint.pprint(data)
    #ip = tsms.find_ip('RAV21')
    #print ip
    #tsms.save_current_page(r'temp/debug.txt')
    #time_list, machine_dict = tsms.get_current_booking(r'temp/debug.txt')
    #pprint.pprint(time_list)
    #pprint.pprint(machine_dict['RAV54'])
    record = tsms.get_my_booking()
    pprint.pprint(record)




