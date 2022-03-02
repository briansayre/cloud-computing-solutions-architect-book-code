'''
MIT License

Copyright (c) 2019 Arshdeep Bahga and Vijay Madisetti

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
'''

#!flask/bin/python
from flask import Flask, jsonify, abort, request, make_response, url_for
from flask import render_template, redirect, session
import os
import boto3    
import time
import datetime
from boto3.dynamodb.conditions import Key, Attr
import exifread
import json

app = Flask(__name__)
app.secret_key = 'whoop'

UPLOAD_FOLDER = os.path.join(app.root_path,'static/media')
ALLOWED_EXTENSIONS = set(['png', 'jpg', 'jpeg'])
AWS_ACCESS_KEY="AKIA2TPIYF2FBOX6X4VA"
AWS_SECRET_KEY="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"
REGION="us-east-1"
BUCKET_NAME="photo-gallery-bucket-gt"

dynamodb = boto3.resource('dynamodb', aws_access_key_id=AWS_ACCESS_KEY,
                            aws_secret_access_key=AWS_SECRET_KEY,
                            region_name=REGION)

table = dynamodb.Table('PhotoGallery')

usertable = dynamodb.Table('PhotoGalleryUsers')

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.errorhandler(400)
def bad_request(error):
    return make_response(jsonify({'error': 'Bad request'}), 400)


@app.errorhandler(404)
def not_found(error):
    return make_response(jsonify({'error': 'Not found'}), 404)

def getExifData(path_name):
    f = open(path_name, 'rb')
    tags = exifread.process_file(f)
    ExifData={}
    for tag in tags.keys():
        if tag not in ('JPEGThumbnail',
                        'TIFFThumbnail',
                        'Filename',
                        'EXIF MakerNote'):    
            key="%s"%(tag)
            val="%s"%(tags[tag])
            ExifData[key]=val
    return ExifData

def s3uploading(filename, filenameWithPath):
    s3 = boto3.client('s3', aws_access_key_id=AWS_ACCESS_KEY,
                            aws_secret_access_key=AWS_SECRET_KEY)
                       
    bucket = BUCKET_NAME
    path_filename = "photos/" + filename
    print path_filename
    s3.upload_file(filenameWithPath, bucket, path_filename)  
    # s3.put_object_acl(ACL='public-read', Bucket=bucket, Key=path_filename)
    return "http://"+BUCKET_NAME+\
        ".s3.amazonaws.com/"+ path_filename  

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/signup', methods=['POST'])
def signup():
    ts=time.time()
    username = request.form['username']
    password = request.form['password']
    usertable.put_item(
            Item={
                    "UserId": str(int(ts*1000)),
                    "username": username,
                    "password": password
                }
            )
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        print("u: " + username + "p: " + password)
        response = usertable.scan(
            FilterExpression=Attr('username').eq(str(username))
        )
        items = response['Items']
        response_password = items[0]['password']
        if (password == response_password):
            session['current_user_id'] = items[0]['UserId']
            print("pass=curr " + str(items[0]['UserId']))
            return redirect(url_for('home_page'), code=200)
        return redirect(url_for('index'), code=505)
    return redirect(url_for('index'), code=505)

@app.route('/logout')
def logout():
   # remove the username from the session if it is there
   session.pop('current_user_id', None)
   return redirect(url_for('index'))

@app.route('/home', methods=['GET', 'POST'])
def home_page():
    # response = table.scan(FilterExpression=Attr('UserId').eq(str(1646174048751)))
    response = table.scan(FilterExpression=Attr('UserId').eq(1646174048751))
    items = response['Items']
    print(items)
    print("USERID: " + str( session['current_user_id'] ))
    return render_template('home.html', photos=items)


@app.route('/add', methods=['GET', 'POST'])
def add_photo():
    if request.method == 'POST':    
        uploadedFileURL=''

        file = request.files['imagefile']
        title = request.form['title']
        tags = request.form['tags']
        description = request.form['description']

        print title,tags,description
        if file and allowed_file(file.filename):
            filename = file.filename
            filenameWithPath = os.path.join(UPLOAD_FOLDER,  filename)
            print filenameWithPath
            file.save(filenameWithPath)
            uploadedFileURL = s3uploading(filename, filenameWithPath)
            ExifData=getExifData(filenameWithPath)
            ts=time.time()
            timestamp = datetime.datetime.\
                        fromtimestamp(ts).\
                        strftime('%Y-%m-%d %H:%M:%S')

            table.put_item(
            Item={
                    "PhotoID": str(int(ts*1000)),
                    "CreationTime": timestamp,
                    "Title": title,
                    "Description": description,
                    "Tags": tags,
                    "URL": uploadedFileURL,
                    "ExifData": json.dumps(ExifData),
                    "UserID": str(session['current_user_id'])
                }
            )

        return redirect('/')
    else:
        return render_template('form.html')

@app.route('/<int:photoID>', methods=['GET'])
def view_photo(photoID):
    response = table.scan(
        FilterExpression=Attr('PhotoID').eq(str(photoID)) & Attr('UserId').eq(str(session['current_user_id']))
    )
    items = response['Items']
    print(items[0])
    tags=items[0]['Tags'].split(',')
    exifdata=json.loads(items[0]['ExifData'])

    return render_template('photodetail.html', 
            photo=items[0], tags=tags, exifdata=exifdata)

@app.route('/search', methods=['GET'])
def search_page():
    query = request.args.get('query', None)    
    
    response = table.scan(
        FilterExpression=Attr('Title').contains(str(query)) | 
                        Attr('Description').contains(str(query)) | 
                        Attr('Tags').contains(str(query)) & 
                        Attr('UserId').eq(str(session['current_user_id']))
    )
    items = response['Items']
    return render_template('search.html', 
            photos=items, searchquery=query)

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=5000)
