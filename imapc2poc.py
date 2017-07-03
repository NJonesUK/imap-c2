import argparse
import socket
import time
import email.message
import threading
import Queue
import base64
from imapclient import IMAPClient

parser = argparse.ArgumentParser()
parser.add_argument("-p", "--port", type=int, help="port to listen on")
parser.add_argument("-u", "--username", help="username for gmail account")
parser.add_argument("-k", "--password", help="password to gmail account")
parser.add_argument("-i", "--id", help='ID of system')
parser.add_argument("-r", "--remoteid", help='ID of the remote system')
args = parser.parse_args()

host = 'imap.gmail.com'
username = args.username
password = args.password
folder = "[Gmail]/Drafts"
ssl = True
instance_id = args.id
remote_id = args.remoteid
inqueue = Queue.Queue()
outqueue = Queue.Queue()


def recv_timeout(socket, timeout=1):
    # make socket non blocking
    socket.setblocking(0)

    # total data partwise in an array
    total_data = []
    data = ''

    # beginning time
    begin = time.time()
    while 1:
        # if you got some data, then break after timeout
        if total_data and time.time() - begin > timeout:
            break

        # if you got no data at all, wait a little longer, twice the timeout
        elif time.time() - begin > timeout * 2:
            break

        # recv something
        try:
            data = socket.recv(8192)
            if data:
                total_data.append(data)
                # change the beginning time for measurement
                begin = time.time()
            else:
                # sleep for sometime to indicate a gap
                time.sleep(0.1)
        except:
            pass

    # join all parts to make final string
    return ''.join(total_data)


def upload_to_gmail():
    server = IMAPClient(host, use_uid=True, ssl=ssl)
    server.login(username, password)
    while True:
        if inqueue.qsize() > 0:
            total_data = ''
            while inqueue.qsize() > 0:
                data = inqueue.get_nowait()
                total_data = total_data + data

            msg = email.message.Message()
            msg['Subject'] = remote_id
            msg['From'] = username
            msg['To'] = username
            msg.set_payload(base64.b64encode(total_data))
            server.append(folder, msg.as_string())


def check_gmail():
    server = IMAPClient(host, use_uid=True, ssl=ssl)
    server.login(username, password)
    server.select_folder(folder)
    server.idle()
    while True:
        result = server.idle_check(10)
        if result:
            server.idle_done()
            messages = server.search([u'NOT', 'DELETED'])
            response = server.fetch(messages, ['FLAGS', 'BODY[HEADER.FIELDS (SUBJECT)]', 'BODY[TEXT]'])
            for_deletion = []
            for msgid, data in response.iteritems():
                if instance_id in data['BODY[HEADER.FIELDS (SUBJECT)]']:
                    outqueue.put_nowait(base64.b64decode(data['BODY[TEXT]']))
                    print "Data received via GMail, sending"
                    for_deletion.append(msgid)
            server.delete_messages(for_deletion)
            server.idle()
        else:
            pass


def read_write_socket():
    serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    serversocket.bind(('localhost', args.port))
    serversocket.listen(1)  # become a server socket, maximum 5 connections
    c, addr = serversocket.accept()
    while True:
        if outqueue.qsize() > 0:
            while outqueue.qsize() > 0:
                data = outqueue.get_nowait()
                c.send(data)
        else:
            data = recv_timeout(c)
            if data:
                print "Data received via socket, sending"
                inqueue.put_nowait(data)
    c.close()


threads = []

upload_thread = threading.Thread(target=upload_to_gmail)
download_thread = threading.Thread(target=check_gmail)
socket_thread = threading.Thread(target=read_write_socket)
threads.append(upload_thread)
threads.append(download_thread)
threads.append(socket_thread)
upload_thread.daemon = True
download_thread.daemon = True
socket_thread.daemon = True
upload_thread.start()
download_thread.start()
socket_thread.start()

while True:
    time.sleep(1)
