# -*- coding: utf-8 -*-
from testcasebase import TestCaseBase
import time
import os
from libs.test_loader import load
import libs.utils as utils
from libs.logger import infoLogger
from libs.deco import multi_dimension
import libs.ddt as ddt
import libs.conf as conf


@ddt.ddt
class TestNameserverMigrate(TestCaseBase):

    leader, slave1, slave2 = (i for i in conf.tb_endpoints)

    def createtable_put(self, tname, data_count):
        metadata_path = '{}/metadata.txt'.format(self.testpath)
        table_meta = {
            "name": tname,
            "ttl": 144000,
            "storage_mode": "kSSD",
            "table_partition": [
                {"endpoint": self.leader,"pid_group": "0-7","is_leader": "true"},
                {"endpoint": self.slave1,"pid_group": "3-7","is_leader": "false"},
                {"endpoint": self.slave2,"pid_group": "0-3","is_leader": "false"},
            ],
            "column_desc":[
                {"name": "k1", "type": "string", "add_ts_idx": "true"},
                {"name": "k2", "type": "string", "add_ts_idx": "false"},
                {"name": "k3", "type": "string", "add_ts_idx": "false"},
            ],
        }
        utils.gen_table_meta_file(table_meta, metadata_path)
        rs = self.ns_create(self.ns_leader, metadata_path)
        self.assertIn('Create table ok', rs)
        table_info = self.showtable(self.ns_leader, tname)
        self.tid = int(table_info.keys()[0][1])
        self.pid = 4
        self.put_large_datas(data_count, 7)

    @ddt.data(
        ('4-6', [4, 5, 6]),
        ('4,6', [4, 6]),
        ('4', [4])
    )
    @ddt.unpack
    def test_ns_client_migrate_normal(self, pid_group, pid_range):
        """
        正常情况下迁移成功
        :param pid_group:
        :param pid_range:
        :return:
        """
        tname = str(time.time())
        self.tname = tname
        self.createtable_put(tname, 100)
        time.sleep(2)
        rs1 = self.get_table_status(self.slave1)
        rs2 = self.get_table_status(self.slave2)
        rs3 = self.migrate(self.ns_leader, self.slave1, tname, pid_group, self.slave2)
        time.sleep(10)
        rs4 = self.showtable(self.ns_leader)
        rs5 = self.get_table_status(self.slave1)
        rs6 = self.get_table_status(self.slave2)
        self.assertIn('partition migrate ok', rs3)
        for i in pid_range:
            self.assertNotIn((tname, str(self.tid), str(i), self.slave1), rs4)
            self.assertIn((tname, str(self.tid), str(i), self.slave2), rs4)
            self.assertIn((self.tid, i), rs1.keys())
            self.assertNotIn((self.tid, i), rs2.keys())
            self.assertNotIn((self.tid, i), rs5.keys())
            self.assertIn((self.tid, i), rs6.keys())
            self.get_latest_opid_by_tname_pid(tname, i)
            self.check_migrate_op(self.latest_opid)

    def test_ns_client_migrate_endpoint_offline(self):
        """
        节点离线，迁移失败
        """
        tname = str(time.time())
        self.createtable_put(tname, 1)
        self.stop_client(self.slave1)
        time.sleep(10)
        self.showtablet(self.ns_leader)
        self.showtable(self.ns_leader, tname)
        rs1 = self.migrate(self.ns_leader, self.slave1, tname, '4-6', self.slave2)
        rs2 = self.migrate(self.ns_leader, self.slave2, tname, '0-2', self.slave1)
        self.start_client(self.slave1)
        time.sleep(10)
        self.assertIn('src_endpoint is not exist or not healthy', rs1)
        self.assertIn('des_endpoint is not exist or not healthy', rs2)

    def test_ns_client_migrate_failover_and_recover(self):  # RTIDB-252
        """
        迁移时发生故障切换，故障切换成功，迁移失败
        原leader故障恢复成follower之后，可以被迁移成功
        :return:
        """
        tname = str(time.time())
        self.createtable_put(tname, 50)
        time.sleep(2)
        rs0 = self.get_table_status(self.leader, self.tid, self.pid)  # get offset leader
        self.stop_client(self.leader)
        time.sleep(2)
        self.offlineendpoint(self.ns_leader, self.leader)
        time.sleep(2)
        self.wait_op_done(tname)
        rs1 = self.migrate(self.ns_leader, self.slave1, tname, '4-6', self.slave2)
        time.sleep(2)
        self.wait_op_done(tname)
        rs2 = self.showtable(self.ns_leader, tname)

        self.start_client(self.leader)  # recover table
        time.sleep(5)
        self.recoverendpoint(self.ns_leader, self.leader)
        time.sleep(2)
        self.wait_op_done(tname)
        self.showtable(self.ns_leader, tname)
        rs6 = self.get_table_status(self.slave1, self.tid, self.pid)  # get offset slave1
        rs3 = self.migrate(self.ns_leader, self.leader, tname, '4-6', self.slave2)
        time.sleep(2)
        self.wait_op_done(tname)
        rs4 = self.showtable(self.ns_leader, tname)
        rs5 = self.get_table_status(self.slave2, self.tid, self.pid)  # get offset slave2
        self.showopstatus(self.ns_leader)

        self.assertIn('failed to migrate partition. error msg: cannot migrate leader', rs1)
        self.assertIn('partition migrate ok', rs3)
        for i in range(4, 7):
            self.assertIn((tname, str(self.tid), str(i), self.slave1), rs2)
            self.assertNotIn((tname, str(self.tid), str(i), self.slave2), rs2)
            self.assertNotIn((tname, str(self.tid), str(i), self.leader), rs4)
            self.assertIn((tname, str(self.tid), str(i), self.slave2), rs4)
        self.assertEqual(rs0[0], rs5[0])
        self.assertEqual(rs0[0], rs6[0])
        self.ns_drop(self.ns_leader, tname)

    def test_ns_client_migrate_no_leader(self):
        """
        无主状态下迁移失败
        :return:
        """
        tname = str(time.time())
        self.createtable_put(tname, 10)
        self.stop_client(self.leader)
        time.sleep(2)
        rs1 = self.migrate(self.ns_leader, self.slave1, tname, "4-6", self.slave2)
        time.sleep(2)
        rs2 = self.showtable(self.ns_leader, tname)

        self.start_client(self.leader)
        time.sleep(10)
        self.showtable(self.ns_leader, tname)
        self.assertIn('partition migrate ok', rs1)
        for i in range(4, 7):
            self.assertIn((tname, str(self.tid), str(i), self.slave1), rs2)
            self.assertNotIn((tname, str(self.tid), str(i), self.slave2), rs2)
        self.ns_drop(self.ns_leader, tname)


if __name__ == "__main__":
    load(TestNameserverMigrate)
