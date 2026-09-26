import socket, threading, json, os, base64, hashlib, secrets, uuid, time
from datetime import datetime, timezone

HOST="0.0.0.0"
PORT=12145
BASE_DIR=os.path.dirname(os.path.abspath(__file__))
ACCOUNTS_FILE=os.path.join(BASE_DIR,"netra_main_accounts.json")
SERVERS_FILE=os.path.join(BASE_DIR,"netra_servers.json")
lock=threading.RLock()
accounts={}
username_map={}
servers={}

def load():
    global accounts, username_map, servers
    try:
        with open(ACCOUNTS_FILE,"r",encoding="utf-8") as f: accounts=json.load(f)
    except Exception: accounts={}
    username_map={v.get("username_normalized",v.get("username","").casefold()):k for k,v in accounts.items()}
    try:
        with open(SERVERS_FILE,"r",encoding="utf-8") as f: servers=json.load(f)
    except Exception: servers={}

def save():
    with open(ACCOUNTS_FILE,"w",encoding="utf-8") as f: json.dump(accounts,f,indent=2)
    with open(SERVERS_FILE,"w",encoding="utf-8") as f: json.dump(servers,f,indent=2)

def valid_name(n):
    return 2<=len(n)<=24 and n==n.strip() and bool(__import__('re').fullmatch(r"[A-Za-z0-9_\- ]+",n))

def pw_hash(p,salt=None):
    salt=base64.b64decode(salt) if salt else secrets.token_bytes(16)
    d=hashlib.pbkdf2_hmac('sha256',p.encode(),salt,180000)
    return base64.b64encode(salt).decode(),base64.b64encode(d).decode()

def auth(action,name,password):
    norm=name.casefold()
    if not valid_name(name): return None,"Username must be 2-24 characters using letters, numbers, spaces, _ or -"
    if not 6<=len(password)<=128: return None,"Password must be 6-128 characters"
    with lock:
        aid=username_map.get(norm)
        if action=="REGISTER":
            if aid: return None,"That username is already registered"
            aid=uuid.uuid4().hex
            salt,digest=pw_hash(password)
            accounts[aid]={"username":name,"username_normalized":norm,"password_salt":salt,"password_hash":digest,"created_at":datetime.now(timezone.utc).isoformat(),"status":"Online","custom_status":""}
            username_map[norm]=aid; save()
            return aid,None
        if not aid: return None,"No account exists with that username"
        rec=accounts[aid]
        _,digest=pw_hash(password,rec.get('password_salt'))
        if not secrets.compare_digest(digest,rec.get('password_hash','')): return None,"Incorrect password"
        return aid,None

def user_line(aid):
    r=accounts[aid]; return f"AUTH_OK:{aid}:{r['username']}"

def handle(conn,addr):
    buf=""
    try:
        while True:
            data=conn.recv(65536)
            if not data: break
            buf+=data.decode('utf-8')
            while '\n' in buf:
                line,buf=buf.split('\n',1)
                if not line: continue
                out=process(line)
                if out is not None: conn.sendall((out+'\n').encode())
    except Exception as e: print('[MAIN ERROR]',addr,e)
    finally: conn.close()

def process(line):
    parts=line.split(':',3); cmd=parts[0]
    if cmd in ('LOGIN','REGISTER') and len(parts)==3:
        try: password=base64.b64decode(parts[2]).decode('utf-8')
        except Exception: return 'AUTH_FAIL:Invalid password data'
        aid,err=auth(cmd,parts[1].strip(),password)
        return user_line(aid) if aid else 'AUTH_FAIL:'+err
    if cmd=='RENAME' and len(parts)==3:
        aid,new=parts[1],parts[2].strip()
        with lock:
            if aid not in accounts: return 'RENAME_FAIL:Account not found'
            if not valid_name(new): return 'RENAME_FAIL:Invalid username'
            norm=new.casefold(); old=accounts[aid]['username']; other=username_map.get(norm)
            if other and other!=aid: return 'RENAME_FAIL:That username is already taken'
            username_map.pop(old.casefold(),None); username_map[norm]=aid
            accounts[aid]['username']=new; accounts[aid]['username_normalized']=norm; save()
            return f'RENAME_OK:{old}:{new}'
    if cmd=='SETSTATUS' and len(parts)>=3:
        aid,status=parts[1],parts[2]
        custom=parts[3] if len(parts)>3 else ''
        with lock:
            if aid in accounts:
                accounts[aid]['status']=status; accounts[aid]['custom_status']=custom; save()
        return 'OK'
    if cmd=='SERVER_REGISTER' and len(parts)==4:
        sid,name,hostport=parts[1],parts[2],parts[3]
        with lock: servers[sid]={'name':name,'host':hostport,'last_seen':time.time()}; save()
        return 'OK'
    if cmd=='USER_LIST':
        with lock: return 'USERS:'+','.join(sorted([r.get('username','') for r in accounts.values()],key=str.lower))
    if cmd=='SERVER_LIST':
        with lock:
            now=time.time(); live={k:v for k,v in servers.items() if now-v.get('last_seen',0)<120}
            servers.update(live)
            return 'SERVERS:'+json.dumps(live,separators=(',',':'))
    if cmd=='PROFILE' and len(parts)==2:
        aid=parts[1]
        with lock:
            if aid not in accounts:return 'PROFILE_FAIL:unknown'
            r=accounts[aid]
            return 'PROFILE:'+json.dumps({'username':r['username'],'status':r.get('status','Online'),'custom_status':r.get('custom_status',''),'created_at':r.get('created_at','')},separators=(',',':'))
    return 'ERROR:Unknown command'

load()
print(f'NETRA MAIN SERVER listening on {HOST}:{PORT}')
print('Central accounts + server directory enabled.')
with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as s:
    s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1); s.bind((HOST,PORT)); s.listen(100)
    while True:
        c,a=s.accept(); threading.Thread(target=handle,args=(c,a),daemon=True).start()
