#!/usr/bin/env python
usage_text = """
LPIRC Referee Server 
====================
@2015 - HELPS, Purdue University

Main Tasks:
-----------
1. Authenticate user and provide time limited token for the session.
2. Send images to token validated client devices upon GET request.
3. Receive asynchronous post results for final evaluation.
4. Get power meter readings from powermeter.

Requirements:
-------------
1. Python v2.7.3
2. Flask - Microframework for Python

Usage:
------
referee.py [OPTION]...
Options:
         -w, --ip
                IP address of the server in format <xxx.xxx.xxx.xxx>
                Default: 127.0.0.1

         -p, --port
                Port number of the server.
                Default: 5000

         --images
                Test images (Relative to root directory)
                Default: images/ILSRVC2012_val/*.JPEG

         --result
                Test results (Relative to root directory)
                Default: result

         --debug
                Run server in debug mode
                Default: debug = None

         -h, --help
                Displays all the available option


Following URLs are recognized, served and issued:
------------------------------------------------
Assumptions:
-----------
1. Image index starts from 1 (not 0).
2. Command line arguments expect to be within quotes

"""
import cgi
from random import randint
import getopt, sys, re, glob, os                                          # Parser for command-line options
from flask import Flask, url_for, send_from_directory, request, Response  # Webserver Microframework
from flask.ext.login import LoginManager, UserMixin, login_required       # Login manager 
from itsdangerous import JSONWebSignatureSerializer                       # Token for authentication


app = Flask(__name__)
login_manager = LoginManager()
login_manager.init_app(app)



#++++++++++++++++++++++++++++++++ Global Variables +++++++++++++++++++++++++++++++++++
host_ipaddress = '127.0.0.1'
host_port = '5000'
test_images_dir_wildcard = '../images/ILSRVC2012_val/*.JPEG'
test_result = 'result'
mode_debug = 'True' #'None'
server_secret_key = 'ITSASECRET'
total_number_images = 0
sent_image_dictionary = []
flag = 0
bin_size=3
#++++++++++++++++++++++++++++++++ URLs +++++++++++++++++++++++++++++++++++++++++++++++
url_root = '/'
url_help = '/help'
url_login = '/login'
url_get_token = '/get_token'
url_verify_token = '/verify'
url_get_image = '/image/'
url_post_result = '/result'

#++++++++++++++++++++++++++++++++ Macros/Form-Fields ++++++++++++++++++++++++++++++++++
ff_username = 'username'
ff_password = 'password'
ff_token = 'token'
ff_image_index = 'image'
ff_class_id = 'CLASS_ID'
ff_confidence = 'confidence'
ff_bb_xmin = 'xmin'
ff_bb_xmax = 'xmax'
ff_bb_ymin = 'ymin'
ff_bb_ymax = 'ymax'


#++++++++++++++++++++++++++++++++ Help URL - Response ++++++++++++++++++++++++++++++++++
server_help_message = ("""
Valid URLs:
            (post/get)     --NA--                            host/
                                                             Example: curl 127.0.0.1:5000/

            (post/get)     --NA--                            host%s
                                                             Example: curl 127.0.0.1:5000%s

            (post)      (%s=[user]&%s=[pass])    host%s
                                                             Example: curl --data "%s=user&%s=pass" 127.0.0.1:5000%s

            (post)      (%s=[token])                      host%s
                                                             Example: curl --data "%s=daksldjsaldkjlkj32....." 127.0.0.1:5000%s

            (post)      (%s=[token]&%s=[image_index])  host%s (Image index starts with 1: 1,2,3,...)
                                                             Example: curl --data "%s=daks....&%s=3" 127.0.0.1:5000%s

            (post)      (%s=[token]&%s=[image_index]&..
                         %s=[id]&%s=[conf]&..
                         %s=[xmin]&%s=[xmax]&..
                         %s=[ymin]&%s=[ymax])            host%s
                                                             Example: curl --data "%s=daks....&%s=3&
                                                                                   %s=7&%s=0.38&
                                                                                   %s=123.00&%s=456.00&
                                                                                   %s=132.00&%s=756.00"     127.0.0.1:5000%s

""" %
    (url_help, url_help, 
     ff_username, ff_password, url_login, 
     ff_username, ff_password, url_login, 
     ff_token, url_verify_token, 
     ff_token, url_verify_token, 
     ff_token, ff_image_index, url_get_image, 
     ff_token, ff_image_index, url_get_image, 
     ff_token, ff_image_index, 
     ff_class_id, ff_confidence, 
     ff_bb_xmin, ff_bb_xmax, 
     ff_bb_ymin, ff_bb_ymax, url_post_result, 
     ff_token, ff_image_index, 
     ff_class_id, ff_confidence, 
     ff_bb_xmin, ff_bb_xmax, 
     ff_bb_ymin, ff_bb_ymax, url_post_result))


resp_login_fail = 'Inavlid username or password'
resp_invalid_token = 'Invalid Token'
resp_valid_token = 'Valid Token'
resp_invalid_image_index = 'Invalid Image index'
resp_image_index_out_of_range = 'Image index out of range'
resp_image_dir_not_exist = 'Image directory does not exist'

#++++++++++++++++++++++++++++++++ Username/Password Database ++++++++++++++++++++++++++
# Minimal Flask-Login Example
# Ref: http://gouthamanbalaraman.com/minimal-flask-login-example.html
class User(UserMixin):
    # proxy for a database of users
    user_database = {"lpirc": ("lpirc", "pass"),
                     "JaneDoe": ("JaneDoe", "Jane"),
                     "user": ("user", "pass"),
                     "JaneDoe": ("JaneDoe", "Jane")}
 
    def __init__(self, username, password):
        self.id = username
        self.password = password
 
    @classmethod
    def get(cls,id):
        return cls.user_database.get(id)



#++++++++++++++++++++++++++++++++ Root url - Response +++++++++++++++++++++++++++++++++++
# Help and Default options
@app.route(url_root,methods=['post','get'])
@app.route(url_help,methods=['post','get'])
def server_help():
    return Response(response=server_help_message, status=200)


#++++++++++++++++++++++++++++++++ login url - Response +++++++++++++++++++++++++++++++++++
# Login function
@app.route(url_login, methods=['post','get'])
@app.route(url_get_token, methods=['post','get'])
def login_check():
    global sent_image_dictionary
    global result_file
    sent_image_dictionary = []
    rx_username = request.form[ff_username]
    rx_password = request.form[ff_password]
    # Validate username and password
    if verify_user_entry(rx_username,rx_password) is None:
        return Response(response=resp_login_fail, status=200)
    else:
        result_file = rx_username
        # Generate Token
        s = JSONWebSignatureSerializer(server_secret_key)
        token = s.dumps({ff_username: rx_username, ff_password : rx_password})
        return Response(response=token, status=200)


#++++++++++++++++++++++++++++++++ Verify Token url - Response +++++++++++++++++++++++++++++
# Verify Token
@app.route(url_verify_token,methods=['post','get'])
def token_check():
    token = request.form[ff_token]
    if verify_user_token(token) is None:
        return Response(response=resp_invalid_token, status=200)
    else:
        return Response(response=resp_valid_token, status=200)


#++++++++++++++++++++++++++++++++ Send Image url - Response ++++++++++++++++++++++++++++++++
# Send Images
@app.route(url_get_image,methods=['post','get'])
def send_image():
    global sent_image_dictionary
    global flag
    global bin_size
    global list_of_images
    token = request.form[ff_token]
    if verify_user_token(token) is None:
        return Response(response=resp_invalid_token, status=200)
    else:
        if flag==0:
            # List all images in directory
            list_of_images = glob.glob(test_images_dir_wildcard)
            flag=1
        # Token Verified, Send back images
        image_index_str = request.args.get('image')
        match = re.search("[^0-9]", image_index_str)
        if match:
            return Response(response=resp_invalid_image_index, status=200)
        image_index = int(image_index_str)
        if (image_index <= 0) or (image_index > total_number_images):
            return Response(response=resp_image_index_out_of_range, status=200)
        # Assuming image index starts with 1. example: 1,2,3,....
        sent_already = [item for item in sent_image_dictionary if item[0] == image_index]
        if not sent_already:
            image_chosen = 1+randint(bin_size*(image_index-1),bin_size-1+(bin_size*(image_index-1)))
            sent_image_dictionary.append((image_index,image_chosen))
        else:
            image_chosen = sent_already[0][1]
        # Flask send file expects split directory arguments
        split_path_image = os.path.split(list_of_images[image_chosen])
        return send_from_directory(split_path_image[0], split_path_image[1], as_attachment=True)        



#++++++++++++++++++++++++++++++++ Log results url - Response ++++++++++++++++++++++++++++++++
# Store result
@app.route("/result",methods=['post'])
def store_result():
    global result_file
    global sent_image_dictionary
    token = request.form['token']
    if verify_user_token(token) is None:
        return Response(response='Invalid User', status=200)
    else:
        # Token Verified, Store results
        form = cgi.FieldStorage()
        image_name = request.form.getlist("image_name")
	CLASS_ID = request.form.getlist("CLASS_ID")
	confidence = request.form.getlist("confidence")
	xmin = request.form.getlist("xmin")
	ymin = request.form.getlist("ymin")
	xmax = request.form.getlist("xmax")
	ymax = request.form.getlist("ymax")
    if len(image_name)==len(CLASS_ID)==len(confidence)==len(xmin)==len(ymin)==len(xmax)==len(ymax)>0:
        s=""
        for item in range(0,len(ymax)):
            if int(image_name[item]) in dict(sent_image_dictionary):
                p=dict(sent_image_dictionary)[int(image_name[item])]    
                s=s+(str(p) + " " + CLASS_ID[item] + " " + confidence[item] + " " + xmin[item] + " " + ymin[item] + " " + xmax[item] + " " + ymax[item] + "\n")
            else:
                print "Image " + image_name[item] + " not requested yet"
        with open('../../'+test_result+'/'+result_file+'.txt','a') as fout:
            fout.write(s)   
            fout.close()    
            return "Result Stored in ../../"+test_result+"/"+result_file+".txt\n"
    else:
        print("Incorrect lines\n")
        return "Incorrect Lines\n"


#++++++++++++++++++++++++++++++++ Internal Functions +++++++++++++++++++++++++++++++++++
# Verify user credentials
def verify_user_entry(a_username,a_password):
    user_entry = User.get(a_username)
    if (user_entry is not None):
        user = User(user_entry[0],user_entry[1])
        if (user.password == a_password):
            return "Valid"
        else:
            return None

    return None

def verify_user_token(a_token):
    s = JSONWebSignatureSerializer(server_secret_key)
    credential = s.loads(a_token)
    if verify_user_entry(credential['username'],credential['password']) is None:
        return None
    else:
        return "Valid"
    

# Script usage function
def usage():
    print usage_text

# Initialize global variables
def init_global_vars():

    global test_images_dir_wildcard   # eg ../../data/images/*.jpg
    global total_number_images

    image_wildcard = os.path.basename(test_images_dir_wildcard)
    image_dirname = os.path.dirname(test_images_dir_wildcard)

    # Check if basename contains wildcard
    if re.search('[\*\.]', image_wildcard) == None:     # Still Folder name or empty
        assert os.path.exists(test_images_dir_wildcard), test_images_dir_wildcard+'--'+resp_image_dir_not_exist
        test_images_dir_wildcard = os.path.join(test_images_dir_wildcard, '*.*')
        
    total_number_images = len(glob.glob(test_images_dir_wildcard))
    print "Found %d test images in %s \n" % (total_number_images, test_images_dir_wildcard)
    return



#++++++++++++++++++++++++++++++++ Parse Command-line Input +++++++++++++++++++++++++++++++
# Main function to parse command-line input and run server
def parse_cmd_line():

    global host_ipaddress
    global host_port
    global test_images_dir_wildcard
    global test_result
    global mode_debug
    global server_secret_key

    try:
        opts, args = getopt.getopt(sys.argv[1:], "hw:p:", ["help", "ip=", "bin=","port=", "images=", "result=", "debug", "secret="])
    except getopt.GetoptError as err:
        # print help information and exit:
        print str(err) 
        usage()
        sys.exit(2)
    for switch, val in opts:
        if switch in ("-h", "--help"):
            usage()
            sys.exit()
        elif switch in ("-w", "--ip"):
            host_ipaddress = val
        elif switch in ("-p", "--port"):
            host_port = val
        elif switch =="--bin":
            bin_size = val
        elif switch == "--images":
            test_images_dir_wildcard = val
        elif switch == "--result":
            test_result = val
        elif switch == "--debug":
            mode_debug = 'True'
        elif switch == "--secret":
            server_secret_key = val
        else:
            assert False, "unhandled option"

    print "\nhost = "+host_ipaddress+":"+host_port+"\nTest Images = "+test_images_dir_wildcard+"\nTest Result = "+test_result+"\nDebug Mode  = "+mode_debug 




#++++++++++++++++++++++++++++++++ Script enters here at beginning +++++++++++++++++++++++++++++++++++
if __name__ == "__main__":
    # Parse Command-line
    parse_cmd_line()
    # Initialize global variables
    init_global_vars()
    # Start server
    app.config["SECRET_KEY"] = server_secret_key
    app.run(host=host_ipaddress, port=int(host_port), debug=mode_debug)


