
import os
import psutil
import socket
import sys
import threading
import time

from distributed_master import *
from valid_server import *

REPORT_TIME_WAIT=5

'''
    Command List :
        Update Module :
            (sender Master) -> -update
            (form    Slave) <- None   
            ---  WARNING! Can not using UDP to tranceport big data ,it will be flash 
            ---  sock recv() buffer and than packet() can not correct resolve data stream
            (sender  Slave) -> connect to TCP port
            (sender  Slave) -> -update
            (form   Master) <- [['%file_index1%':'%file_index1_data%'],['%file_index2%':'%file_index2_data%'],...]
            
        Collect Data :
            (sender  Slave) -> -report {'IP':'%slave_ip%','CPU':%cpu_rate%,'Memory':%memory_using%,'PoCFile':%poc_file_count%}
            (form   Master) <- None
        
        Upload PoC :
            (sender Master) -> -upload
            (form    Slave) <- None
            ---
            (sender  Slave) -> connect to TCP port
            (sender  Slave) -> -upload [['%file_index1%':'%file_index1_data%'],['%file_index2%':'%file_index2_data%'],...]
            (form   Master) <- OK
            
        Discover Master :
            (sender  Slave) -> -discover
            (form   Master) <- -discover %master_ip%
'''

def get_cpu_rate() :
    cpu_data_list=psutil.cpu_percent(interval=REPORT_TIME_WAIT,percpu=True)
    cpu_rate=0.0
    for cpu_data_index in cpu_data_list :
        cpu_rate+=cpu_data_index
    cpu_rate/=psutil.cpu_count()
    return cpu_rate
    
def get_memory_rate() :
    memory_data=psutil.virtual_memory()
    return memory_data.percent

def poc_file_count() :
    file_count=0
    for file_name in os.listdir(CONFIG_POC_PATH):
        if file_name.find(EXTANSION_NAME_POC)>0 :
            file_count+=1
    return file_count

class tcp_client() :
    def __init__(self,dest_address) :
        self.sock=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        self.sock.connect((dest_address,TCP_PORT))
        
    def send(self,data) :
        self.sock.send(data)
        
    def recv(self) :
        return self.sock.recv(DATA_LENGTH)
    
    def close(self) :
        self.sock.close()

class distributed_slave() :
    def __init__(self) :
        self.broadcast=broadcast()
        
    def __get_current_path(self) :
        path = sys.path[0]
        if os.path.isdir(path):
            return path
        return os.path.dirname(path)
        
    def get_master_ip(self) :  #  WARNING !!! it will make a bug ,broadcast can not recv command 
                               #  because Thread __background_server_report_thread will call recv()
                               #  so discover data will trace to __background_server_report_thread not this
                               #  it is a probleam about thread lock()
        packet_data=packet()
        packet_data.set_slave()
        packet_data.set_slave_command(COMMAND_DISCOVER)
        self.broadcast.send(packet_data.tostring())

        self.broadcast.recv()  #  first recv is discover command
        packet_data.resolve(self.broadcast.recv())
        
        if packet_data.get_master() :
            command=packet_data.get_slave_command()
            if valid_command(COMMAND_DISCOVER,command) :
                return split_command_data(command)
        return ''
        
    def __background_server_upload_thread(self) :
        mutex=threading.Lock()
        if mutex.acquire() :
            file_count=0
            file_list=[]
            for file_name in os.listdir(BASE_DIR):
                if file_name.find(EXTANSION_NAME_POC)>0 :
                    file_count+=1
                    file_path=dir_path+'\\'+file_name
                    file_data=open(file_path)
                    if file_data :
                        file_index=[]
                        file_index.append(file_path)
                        file_index.append(file_data.read())
                        file_data.close()
                        file_list.append(file_index)
            trance_data=COMMAND_UPLOAD+' '+str(file_list)
            master_ip=self.get_master_ip()
            tcp_client_=tcp_client(master_ip)
            tcp_client_.send(trance_data)
            tcp_client_.close()
            mutex.release()
        
    def __background_server_thread(self) :
        while True :
            data_packet=packet()
            data_packet.resolve(self.broadcast.recv())
            if data_packet.get_master() :
                command=data_packet.get_slave_command()
                if valid_command(COMMAND_UPDATE,command) :
                    upload_thread=threading.Thread(target=self.__background_server_upload_thread)
                    upload_thread.start()
                elif valid_command(COMMAND_UPLOAD,command) :
                    pass
        
    def __background_server_report_thread(self) :
        while True :
            data_packet=packet()
            data_packet.set_slave()
            data_packet_command='{\'IP\':\''+get_local_ip()+'\',\'CPU\':'+str(get_cpu_rate())+',\'Memory\':'+str(get_memory_rate())+',\'PoCFile\':'+str(poc_file_count())+'}'  #  time wait in get_cpu_rate()
            data_packet.set_slave_command(COMMAND_REPORT+' '+data_packet_command)
            self.broadcast.send(data_packet.tostring())
        
    def run(self) :
        self.server_thread=threading.Thread(target=self.__background_server_thread)
        self.server_thread.start()
        
        self.report_thread=threading.Thread(target=self.__background_server_report_thread)
        self.report_thread.start()
    
    def exit(self) :
        self.server_thread.stop()
        self.report_thread.stop()
        
if __name__=='__main__' :
    distributed_slave_=distributed_slave()
    print distributed_slave_.get_master_ip()
    distributed_slave_.run()
    print 'Distributed Slave Will Exit!'
    