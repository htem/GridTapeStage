#!/usr/bin/env python
"""
Do all operations as index
"""

slot_types = ['slot', 'leader', 'trailer']


class ReelError(Exception):
    pass


class Reel(object):
    def __init__(self, n_slots):
        self.n_slots = n_slots
        self.n_leader = None  # unknown for no version reels
        self._to_index = {
            'leader': lambda v: None,
            'slot': lambda v: None,
            'trailer': lambda v: None,
        }
        self._from_index = {
            'leader': lambda i: None,
            'slot': lambda i: None,
            'trailer': lambda i: None,
        }

    def is_valid_barcode_value(self, value):
        return value < 30000

    def validate_slot_id(self, slot_id, slot_type):
        if slot_type not in slot_types:
            raise ValueError("Unknown slot type: %s" % slot_type)
        if slot_id < 0:
            raise ReelError("Invalid slot id: %s < 0" % slot_id)
        if slot_type in ('leader', 'trailer') and slot_id >= self.n_leader:
            raise ReelError(
                "Invalid slot id: %s >= %s" % (slot_id, self.n_leader))
        elif slot_type == 'slot' and slot_id >= self.n_slots:
            raise ReelError(
                "Invalid slot_id: %s >= %s" % (slot_id, self.n_slots))

    def validate_slot_index(self, slot_index):
        if not isinstance(slot_index, int):
            raise TypeError(
                "Invalid slot_index type %s != int" % type(slot_index))
        if slot_index < 0:
            raise ReelError("Invalid slot_index: %s < 0" % slot_index)
        n_indices = self.n_leader * 2 + self.n_slots
        if slot_index >= n_indices:
            raise ReelError(
                "Invalid slot_index: %s >= %s" % (slot_index, n_indices))

    def slot_id_to_index(self, slot_id, slot_type):
        self.validate_slot_id(slot_id, slot_type)
        slot_index = self._to_index[slot_type](slot_id)
        self.validate_slot_index(slot_index)
        return slot_index

    def slot_index_to_id(self, slot_index):
        self.validate_slot_index(slot_index)
        if (slot_index < self.n_leader):
            slot_type = 'leader'
        elif (slot_index < (self.n_leader + self.n_slots)):
            slot_type = 'slot'
        else:
            slot_type = 'trailer'
        slot_id = self._from_index[slot_type](slot_index)
        self.validate_slot_id(slot_id, slot_type)
        return slot_id, slot_type

    def offset_slot_id(self, slot_id, slot_type, offset):
        # convert current slot id and type to index
        i = self.slot_id_to_index(slot_id, slot_type)
        # offset to determine type and id (or off reel)
        return self.slot_index_to_id(i + offset)


class ReelVersion0(Reel):
    """
    for version 0 (168 leader)
    start_leader: (168 - 1)
        index = 168 - v
    slots: (0 - (n_slots-1))
        index = v + 168
    end_leader: (168 - 1) ?
        index = 168 - v + n_slots + 168
    """
    def __init__(self, n_slots):
        super(ReelVersion0, self).__init__(n_slots)
        self.n_leader = 168
        self._to_index = {
            'leader': lambda v: 168 - v,
            'slot': lambda v: v + 168,
            'trailer': lambda v: 168 - v + self.n_slots + 168,
        }
        self._from_index = {
            'leader': lambda i: 168 - i,
            'slot': lambda i: i - 168,
            'trailer': lambda i: 168 + self.n_slots + 168 - i,
        }

    def is_valid_barcode_value(self, value):
        return value < self.n_slots

    def validate_slot_id(self, slot_id, slot_type):
        if slot_type not in slot_types:
            raise ValueError("Unknown slot type: %s" % slot_type)
        if slot_id < 0:
            raise ReelError("Invalid slot id: %s < 0" % slot_id)
        if slot_type in ('leader', 'trailer'):
            if slot_id > self.n_leader:
                raise ReelError(
                    "Invalid slot id: %s > %s" % (slot_id, self.n_leader))
            elif slot_id == 0:
                raise ReelError("Invalid slot_id: %s == 0" % slot_id)
        elif slot_type == 'slot' and slot_id >= self.n_slots:
            raise ReelError(
                "Invalid slot_id: %s >= %s" % (slot_id, self.n_slots))


class ReelVersion1(Reel):
    """
    for version 1 (170 leader) [ppc, cb3?]
    start_leader: delta = -1
        index = 170 - v - 1
    slots: delta = 1
        index = v + 170
    end_leader: delta = -1
        index = (170 - v - 1) + n_slots + 170
    """
    def __init__(self, n_slots):
        super(ReelVersion1, self).__init__(n_slots)
        self.n_leader = 170
        self._to_index = {
            'leader': lambda v: 170 - v - 1,
            'slot': lambda v: v + 170,
            'trailer': lambda v: 170 - v - 1 + self.n_slots + 170,
        }
        self._from_index = {
            'leader': lambda i: 170 - 1 - i,
            'slot': lambda i: i - 170,
            'trailer': lambda i: 170 - 1 + self.n_slots + 170 - i,
        }

    def is_valid_barcode_value(self, value):
        return value < self.n_slots


class ReelVersion2(Reel):  # TODO subclass v1?
    """
    for version 2 (170 leader)
    start_leader: delta = -1, offset 100000
        index = 170 - v - 1 - 100000
    slots: delta = 1
        index = v + 170
    end_leader: delta = -1, offset 200000
        index = (170 - v - 1 - 200000) + n_slots + 170
    """
    def __init__(self, n_slots):
        super(ReelVersion2, self).__init__(n_slots)
        self.n_leader = 170
        self._to_index = {
            'leader': lambda v: 170 - (v - 100000) - 1,
            'slot': lambda v: v + 170,
            'trailer': lambda v: 170 - (v - 200000) - 1 + self.n_slots + 170,
        }
        self._from_index = {
            'leader': lambda i: 170 - 1 - i + 100000,
            'slot': lambda i: i - 170,
            'trailer': lambda i: 170 - 1 + self.n_slots + 170 - i + 200000,
        }

    def is_valid_barcode_value(self, value):
        if (value > 199999):  # trailer
            return value < 200170
        if (value > 99999):  # leader
            return value < 100170
        # slot
        return value < self.n_slots

    def validate_slot_id(self, slot_id, slot_type):
        if slot_type not in slot_types:
            raise ValueError("Unknown slot type: %s" % slot_type)
        if slot_type == 'leader':
            offset = 100000
            n = self.n_leader
        elif slot_type == 'trailer':
            offset = 200000
            n = self.n_leader
        else:
            offset = 0
            n = self.n_slots
        if slot_id < offset:
            raise ReelError("Invalid slot id: %s < %s" % (slot_id, offset))
        if slot_id >= offset + n:
            raise ReelError(
                "Invalid slot id: %s >= %s" % (slot_id, offset + n))


def create_reel(version, n_slots):
    klass = {
        0: ReelVersion0,
        1: ReelVersion1,
        2: ReelVersion2,
    }.get(version, None)
    if klass is None:
        raise ValueError("Unknown reel version %s" % version)
    return klass(n_slots)


def test():
    rs = [
        ReelVersion0(168),
        ReelVersion1(170),
        ReelVersion2(170),
    ]
    for r in rs:
        n = r.n_slots + r.n_leader * 2
        for i in xrange(n):
            sid, st = r.slot_index_to_id(i)
            pi = r.slot_id_to_index(sid, st)
            assert pi == i
