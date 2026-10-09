"""Original node and bounded request-anchor checks; no provider calls."""
import copy
import unittest
from test_source_cycle import fixture
from select_cycle_anchors import select_cycle_anchors
from prepare_site import network


class CycleAnchorTests(unittest.TestCase):
    def test_source_nodes_order_and_five_or_split_request_budget(self):
        data=fixture();original=copy.deepcopy(data);coords,edges,_=network(data)
        nodes=list(range(20))+[0]
        for count in (5,11):
            result=select_cycle_anchors(data,nodes,count)
            self.assertEqual(count,len(result['indices']))
            self.assertEqual(sorted(set(result['indices'])),result['indices'])
            self.assertTrue(all(0<i<len(nodes)-1 for i in result['indices']))
            self.assertEqual(count,result['maximum'])
            self.assertLess(result['source_shortcut_loss_m'],.001)
        self.assertEqual(original,data)

    def test_limits_and_unmapped_or_repeated_cycle_are_rejected(self):
        data=fixture();nodes=list(range(20))+[0]
        for args in ({'work_limit':0},{'time_limit':0}):
            with self.assertRaises(TimeoutError):select_cycle_anchors(data,nodes,**args)
        for invalid in ([0,1,2,3,4,5,6,7,0],nodes[:-1]+[1],nodes[:10]+[5]+nodes[10:]):
            with self.assertRaises(ValueError):select_cycle_anchors(data,invalid)
        with self.assertRaises(ValueError):select_cycle_anchors(data,nodes,maximum=12)


if __name__=='__main__':unittest.main()
