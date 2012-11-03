##
#   SIMPLE WEB PORTAL FOR HOSTING E-BOOKS
#
#   @author karthik
#   @date Sept 2012
#

### imports
import boto
from boto.s3.key import Key

from flask import Flask, request, session, g, redirect, url_for, escape, abort, \
     render_template, flash

##############################################################################################################


### config 

#access info for aws
USER_NAME="<aws user name>"
AWS_ACCESS_KEY="<aws access key>"
AWS_SECRET_KEY="<aws secret key>"

#s3 config
ALLOWED_EXTENSIONS = set(['pdf'])

#flask config
SECRET_KEY = 'dev key'
DEBUG=True

#login info
ADMIN_PASS="pass"

#other
#simpledb
USER_TABLE = "<user domain name>"
BOOK_TABLE = "<book domain name>"
#s3
BUCKET_NAME = "<s3 bucket name>"



##############################################################################################################


### craeting application
app = Flask(__name__)
app.config.from_object(__name__)


##############################################################################################################


### global vars

#related to simple db entries
sdb = None
domain_user = None
user_entries = None
domain_book = None
book_entries = None

#related to s3 entries
s3 = None
bucket = None

#others
username_list = None
book_isbn_list = None


##############################################################################################################


### connect to simpleDB and s3 and obtain domains and buckets
@app.before_first_request
def connect_db_s3():
    
    # connect to simple db
    global sdb
    sdb = boto.connect_sdb(AWS_ACCESS_KEY, AWS_SECRET_KEY)

    global domain_user
    domain_user = sdb.get_domain(USER_TABLE)   # item.name=username user_type user_pass

    global domain_book
    domain_book = sdb.get_domain(BOOK_TABLE) # item.name = isbn book_name book_author book_desc

    #get list of registered users
    global username_list
    username_list = [item.name for item in domain_user]

    #get list of available books
    global book_isbn_list
    book_isbn_list = [item.name for item in domain_book]

    global book_entries
    book_entries = [dict(isbn=item.name, bookname=item['book_name'], author=item['book_author'], description=item['book_desc']) for item in domain_book]


    # connect to s3
    global s3
    s3 = boto.connect_s3(AWS_ACCESS_KEY, AWS_SECRET_KEY)

    global bucket
    bucket = s3.get_bucket(BUCKET_NAME) 

    session['admin_logged_in'] = False


############################################################################################################## 



### home page
@app.route('/', methods=['GET', 'POST'])
def login():
    error = None

    if request.method == 'POST':
        
        ##check for client is admin
        if request.form['username'] == "admin":
            if request.form['password'] == ADMIN_PASS:
                # log him in and grant permission to visit all pages
                session['admin_logged_in'] = True
                session['author_logged_in'] = True
                session['reader_logged_in'] = True

                return redirect(url_for('admin_page'))
            else:
                error = 'Invalid password'
        
        #if not admin
        else:
            
            #check if client is registered user
            if request.form['username'] not in username_list:
                error = 'Invalid username'
            
            #else if the client is indeed registered
            else:
                #get that client's password and type
                client = domain_user.get_item(request.form['username'])
                client_password, client_type = client['user_pass'], client['user_type']

                #check if the client's password is same as that stored in database
                if request.form['password'] != domain_user.get_item(request.form['username'])['user_pass']:
                    error = 'Invalid password'
                
                # client is authentic,
                else:
                    
                    #redirect the client based on his type and grant appropriate permissions
                    if client_type == "Author":
                        session['author_logged_in'] = True
                        session['reader_logged_in'] = True
                        return redirect(url_for('author_page'))

                    elif client_type == "Reader":
                        session['reader_logged_in'] = True
                        return redirect(url_for('reader_page'))

    return render_template('login.html', error=error)



### logout page = login page
@app.route('/logout')
def logout():
    error=None
    session.pop('admin_logged_in', None)
    session.pop('author_logged_in', None)
    session.pop('reader_logged_in', None)
    return render_template('login.html', error=error)


############################################################################################################## 



### admin page
@app.route('/admin', methods=['GET', 'POST'])
def admin_page():
    # getting user table
    global user_entries
    user_entries = [dict(username=item.name, password=item['user_pass'], type=item['user_type']) for item in domain_user]

    return render_template("admin.html", error=None, entries=user_entries)



### function for adding user entry to simpleDB
@app.route('/user_added', methods=['POST'])
def add_user_entry():
    
    #check if the user already exists to avoid duplicates
    if request.form['username'] not in username_list:
        username_list.append(request.form['username'])

        item = domain_user.new_item(request.form['username'])
        item[ 'user_type' ] = request.form['type']
        item[ 'user_pass' ] = request.form['password']

        item.save()

        global user_entries
        user_entries.append(dict(username=item.name, password=item['user_pass'], type=item['user_type']))
        message = "User Added Successfully"
        
    else:
        message = "User already Exists"
    
    #render the page
    return render_template("admin.html", error=message, entries=user_entries)



### function for deleting user entry from simpleDB
@app.route('/user_deleted/<del_username>', methods=['GET'])
def delete_user_entry(del_username=None):

    #since this function supports GET method, its necessary to check if admin has logged in
    if session['admin_logged_in'] == True:
    
        item = domain_user.get_item(del_username)
        domain_user.delete_item(item)

        #remove from the list
        global user_entries
        user_entries = [entry for entry in user_entries if entry.get('username') != del_username]

        username_list.remove(del_username)


        message = "User Deleted Successfully"

    else:
        message = "You are not authorised! Log in as admin please!!"

    #render the page
    return render_template("admin.html", error=message, entries=user_entries)



### function for deleting book entry from simple db (and the book itself from s3 if it exists)
@app.route('/book_deleted/<del_book_isbn>', methods=['GET'])
def delete_book(del_book_isbn=None):

    #since this function supports GET method, its necessary to check if admin has logged in
    if session['admin_logged_in'] == True:
    
        #remove from simple db
        item = domain_book.get_item(del_book_isbn)
        domain_book.delete_item(item)

        #remove from s3
        k = Key(bucket)
        k.key = "ebooks/"+del_book_isbn+".pdf"  # set key name to isbn
        bucket.delete_key(k)

        #remove from the list
        global book_entries
        book_entries = [entry for entry in book_entries if entry.get('isbn') != del_book_isbn]

        book_isbn_list.remove(del_book_isbn)


        message = "Book Deleted Successfully"

    else:
        message = "You are not authorised! Log in as admin please!!"

    #render the page
    return render_template("author.html", error=message, entries=book_entries)


#############################################################################################################################


### reader page
@app.route('/reader', methods=['GET'])
def reader_page():
    return render_template("reader.html", error=None, entries=book_entries)


#############################################################################################################################


### author page
@app.route('/author', methods=['GET', 'POST'])
def author_page():
    return render_template("author.html", error=None, entries=book_entries)


@app.route('/book_added', methods=['POST'])
def add_book_entry():

    message = ""
    
    #check if the user already exists to avoid duplicates
    if request.form['isbn'] not in book_isbn_list:
        book_isbn_list.append(request.form['isbn'])

        # enter the details into simple db
        item = domain_book.new_item(request.form['isbn'])
        item[ 'book_name' ] = request.form['bookname']
        item[ 'book_author' ] = request.form['author']
        item[ 'book_desc' ] = request.form['description']

        item.save()

        # upload book to s3
        if request.files['file'] != None:
            f=request.files['file']
            k = Key(bucket)
            k.key = "ebooks/"+item.name+".pdf"  # set file name to isbn

            k.set_contents_from_file(f)
            k.make_public()

            message = "E-Book Uploaded"

        global book_entries
        book_entries.append(dict(isbn=item.name, bookname=item['book_name'], author=item['book_author'], description=item['book_desc']))

        message = "Book Added Successfully! " + message

    else:
        message = "Book already Exists!"
    
    #render the page
    return render_template("author.html", error=message, entries=book_entries)

#############################################################################################################################


if __name__ == '__main__':
    app.run(host="<ec2 public IP address>", port=80)
