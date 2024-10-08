import os
import pathlib


from flask import (Flask, flash, redirect, render_template, request, send_file,
                   session, url_for)
from flask_socketio import SocketIO, emit, join_room, leave_room, rooms, send
from werkzeug.utils import secure_filename

path = pathlib.Path(__file__).parent.resolve()
UPLOAD_FOLDER = path / "files"
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'mp3'}

app = Flask(__name__)
app.config['SECRET_KEY'] = 'abcd'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

socketio = SocketIO(app, manage_session=False)

groups = {}
users = {}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/', methods=['POST', 'GET'])
def login():
    session.clear()
    if request.method == 'POST':
        session['email'] = request.form.get('email')
        session['userName'] = request.form.get('userName')
        session['city'] = request.form.get('city')

        if session["email"] in users:
            return render_template('login.html', error="Este email já está em uso", userName=session["userName"], city=session["city"])
        else:
            users[session["email"]] = None;

        return redirect(url_for('lobby'))

    return render_template('login.html')

@app.route('/downloads')
def downloadFile():
    fileName = request.args.get('fileName')
    path = pathlib.Path(__file__).parent.resolve()
    print(path / "files" / fileName)
    return send_file(path / "files" / fileName, as_attachment=True)

@app.route('/lobby', methods=['POST', 'GET'])
def lobby():
    if request.method == 'POST':
        if "create-group" in request.form:
            groupName = request.form.get('groupName')
            session['groupName'] = groupName
            if groupName in groups:
                return render_template('lobby.html', userName=session['userName'], error='Uma sala com este nome já existe', chats = list(groups.keys()))
            groups[session['groupName']] = {"members": {}, "messages": [], "admin" : session["email"]}
            emit("groupUpdate", {"groups" : list(groups.keys())}, to="lobby",namespace="/chat/request")
        
        
        return redirect(url_for('grupo'))
    return render_template('lobby.html', userName=session['userName'], chats = list(groups.keys()))

@app.route('/grupo', methods=['GET', 'POST'])
def grupo():
    if "groupName" not in session:
        session["groupName"] = users[session["email"]]
    if session is None or session["groupName"] not in groups:
        return redirect(url_for("login"))
    
    if request.method == 'POST':
        if "profile" in request.form:
            session["lookupProfile"] = request.form.get("profile")
            return redirect(url_for("profile"))
        else:
                if 'file' not in request.files:
                    flash('No file part')
                    return redirect(request.url)
                file = request.files['file']
                if file.filename == '':
                    flash('No selected file')
                    return redirect(request.url)
                if file and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    else:
        return render_template('grupo.html', groupName = session['groupName'])

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    profile = session["lookupProfile"]
    groupName = session["groupName"]
    if profile == session["email"]:
        return render_template("profile.html", name=session["userName"], email=profile, city= session["city"])
    else:
        return render_template("profile.html", name=groups[groupName]["members"][profile]["userName"], email=profile,
                               city =  groups[groupName]["members"][profile]["userCity"])

@socketio.on("connect", namespace="/chat/messages")
def connect():
    groupName = session.get("groupName")
    userName = session.get("userName")
    userMail = session.get("email")
    userCity = session.get("city")

    if not groupName or not userName:
        return
    if groupName not in groups:
        leave_room(groupName)
        return
    
    if session["email"] == groups[groupName]["admin"]:
        join_room(session["email"])
    join_room(groupName)
    send({"userName": userName, "message": "entrou no grupo"}, to=groupName)
    groups[groupName]["members"][userMail] = {"userName" : userName, "userCity" : userCity}
    emit("userUpdate", groups[groupName]["members"] , to=groupName)
    print(f"{userName} entrou no grupo {groupName}")

@socketio.on("connect", namespace="/chat/request")
def connect():
    join_room("lobby")
    print("Estou no lobby")




@socketio.on("disconnect", namespace="/chat/messages")
def disconnect():
    groupName = session.get("groupName")
    userName = session.get("userName")
    userMail = session.get("email")
    leave_room(groupName)

    print(userMail)
    print(groups[groupName]["members"])


    if groupName in groups: 
        if userMail in groups[groupName]["members"]:
            del groups[groupName]["members"][userMail]
        if len(groups[groupName]["members"]) <= 0:
            del groups[groupName]
            emit("groupUpdate", {"groups" : list(groups.keys())}, to="lobby",namespace="/chat/request")
    
    send({"userName": userName, "message": "saiu do grupo"}, to=groupName)
    if session["groupName"] in groups:
        emit("userUpdate", groups[groupName]["members"] , to=groupName)
    print(f"{userName} saiu do grupo {groupName}")

@socketio.on("message", namespace="/chat/messages")
def message(data):
    
    groupName = session.get("groupName")
    
    if groupName not in groups:
        return 
    
    content = {
        "userName": session.get("userName"),
        "message": data["data"][0],
        "isFile": data["data"][1]
    }
    send(content, to=groupName)
    groups[groupName]["messages"].append(content)
    print(f"{session.get('userName')} said: {data['data']} [chat = {groupName}]")


@socketio.on("peerRequest", namespace="/chat/request")
def peerRequest(data):
    join_room(session["email"])
    users[session["email"]] = data["group"]
    emit('adminRequest', {"name" : session["userName"], "email": session["email"], "group" : data["group"]}, to=groups[data["group"]]["admin"], namespace="/chat/messages")

@socketio.on("adminResponse", namespace="/chat/messages")
def adminResponse(data):
    session["groupName"] = data["group"]
    emit("peerAction", {"response" : data["response"], "group": data["group"], "url" : url_for("grupo")}, to=data["email"], namespace="/chat/request")



    

if __name__ == '__main__':
    socketio.run(app, debug=True, host="0.0.0.0", port=5000)