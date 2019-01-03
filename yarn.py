import time
import subprocess
from subprocess import check_output
from copy import deepcopy
import collectd
import sys
from os import path
import os
import write_json
from utils import * # pylint: disable=W
sys.path.append(path.dirname(path.abspath("/opt/collectd/plugins/sf-plugins-hadoop/Collectors/configuration.py")))
sys.path.append(path.dirname(path.abspath("/opt/collectd/plugins/sf-plugins-hadoop/Collectors/hadoopClusterCollector/yarn_stats.py")))
sys.path.append(path.dirname(path.abspath("/opt/collectd/plugins/sf-plugins-hadoop/Collectors/requirements.txt")))

from configuration import *
from yarn_stats import run_application, initialize_app

class YarnStats:
    def __init__(self):
        """Plugin object will be created only once and \
           collects yarn statistics info every interval."""
        self.retries = 3

    def check_fields(self, line, dic_fields):
        for field in dic_fields:
            if (field+"=" in line or field+" =" in line):
                return field
        return None

    def update_config_file(self, previous_json_yarn):
        file_name = "/opt/collectd/plugins/sf-plugins-hadoop/Collectors/configuration.py"
        lines = []
        flag = 0
        previous_json_yarn = previous_json_yarn.strip(".")
        dic_fields = {"resource_manager": resource_manager,"elastic": elastic, "indices": indices, "previous_json_yarn": previous_json_yarn, "tag_app_name": tag_app_name}
        with open(file_name, "r") as read_config_file:
            for line in read_config_file.readlines():
                field = self.check_fields(line, dic_fields)
                if field and ("{" in line and "}" in line):
                    lines.append("%s = %s\n" %(field, dic_fields[field]))
                elif field or flag:
                    if field:
                        if field == "previous_json_yarn":
                            lines.append('%s = "%s"\n' %(field, dic_fields[field]))
                        else:
                            lines.append("%s = %s\n" %(field, dic_fields[field]))
                    if field and "{" in line:
                        flag = 1
                    if "}" in line:
                        flag = 0
                else:
                    lines.append(line)
        read_config_file.close()
        with open(file_name, "w") as write_config:
            for line in lines:
                write_config.write(line)
        write_config.close()

    def run_cmd(self, cmd, shell, ignore_err=False, print_output=False):
        """
        return output and status after runing a shell command
        :param cmd:
        :param shell:
        :param ignore_err:
        :param print_output:
        :return:
        """
        for i in xrange(self.retries):
            try:
                output = subprocess.check_output(cmd, shell=shell)
                if print_output:
                    print output
                    return output
                return
            except subprocess.CalledProcessError as error:
                if not ignore_err:
                    print >> sys.stderr, "ERROR: {0}".format(error)
                    sleep(0.05)
                    continue
                else:
                    print >> sys.stdout, "WARNING: {0}".format(error)
                    return
        sys.exit(1)

    def get_elastic_search_details(self):
        try:
            with open("/opt/collectd/conf/elasticsearch.conf", "r") as file_obj:
                for line in file_obj.readlines():
                    if "URL" not in line:
                        continue
                    elastic_search = line.split("URL")[1].split("//")[1].split("/")
                    index = elastic_search[1].strip("/").strip("_doc")
                    elastic_search = elastic_search[0].split(":")
                    return elastic_search[0], elastic_search[1], index
        except IOError:
            collectd.error("Could not read file: /opt/collectd/conf/elasticsearch.conf")

    def get_app_name(self):
        try:
            with open("/opt/collectd/conf/filters.conf", "r") as file_obj:
                for line in file_obj.readlines():
                    if 'MetaData "_tag_appName"' not in line:
                        continue
                    return line.split(" ")[2].strip('"')
        except IOError:
            collectd.error("Could not read file: /opt/collectd/conf/filters.conf")

    def read_config(self, cfg):
        """Initializes variables from conf files."""
        for children in cfg.children:
            if children.key == INTERVAL:
                self.interval = children.values[0]
            elif children.key == YARN_NODE:
                resource_manager["hosts"]  = children.values[0].split(",")
            elif children.key == RESOURCE_MANAGER_PORT:
                resource_manager["port"]  = children.values[0]
        host, port, index = self.get_elastic_search_details()
        elastic["host"] = host
        elastic["port"] = port
        indices["yarn"] = index
        appname = self.get_app_name()
        tag_app_name['yarn'] = appname
        self.update_config_file(previous_json_yarn)
        cmd = "pip install -r /opt/collectd/plugins/sf-plugins-hadoop/Collectors/requirements.txt"
        self.run_cmd(cmd, shell=True, ignore_err=True)
        initialize_app()


    @staticmethod
    def add_common_params(namenode_dic, doc_type):
        """Adds TIMESTAMP, PLUGIN, PLUGIN_INS to dictionary."""
        hostname = gethostname()
        timestamp = int(round(time.time()))

        namenode_dic[HOSTNAME] = hostname
        namenode_dic[TIMESTAMP] = timestamp
        namenode_dic[PLUGIN] = 'yarn'
        namenode_dic[ACTUALPLUGINTYPE] = 'yarn'
        namenode_dic[PLUGINTYPE] = doc_type

    def collect_data(self):
        """Collects all data."""
        data = run_application(0)
        docs = [{"NumRebootedNMs": 0, "_documentType": "yarnStatsClusterMetrics", "NumDecommissionedNMs": 0, "name": "Hadoop:service=ResourceManager,name=ClusterMetrics", "AMLaunchDelayNumOps": 0, "_tag_context": "yarn", "AMRegisterDelayNumOps": 0, "_tag_clustermetrics": "ResourceManager", "modelerType": "ClusterMetrics", "NumLostNMs": 0, "time": 1543301379, "_tag_appName": "hadoopapp1", "NumUnhealthyNMs": 0, "AMRegisterDelayAvgTime": 0, "NumActiveNMs": 0, "AMLaunchDelayAvgTime": 0}]
        for doc in docs:
            self.add_common_params(doc, doc['_documentType'])
            write_json.write(doc)

    def read(self):
        self.collect_data()

    def read_temp(self):
        """
        Collectd first calls register_read. At that time default interval is taken,
        hence temporary function is made to call, the read callback is unregistered
        and read() is called again with interval obtained from conf by register_config callback.
        """
        collectd.unregister_read(self.read_temp) # pylint: disable=E1101
        collectd.register_read(self.read, interval=int(self.interval)) # pylint: disable=E1101

namenodeinstance = YarnStats()
collectd.register_config(namenodeinstance.read_config) # pylint: disable=E1101
collectd.register_read(namenodeinstance.read_temp) # pylint: disable=E1101
