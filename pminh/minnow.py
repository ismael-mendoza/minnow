from __future__ import division, print_function

import numpy as np
import numpy.random as random
import struct
import abc

import pminh.bit as bit

MAGIC = 0xacedad
VERSION = 1

int64_group = 0
int32_group = 1
int16_group = 2
int8_group = 3

uint64_group = 4
uint32_group = 5
uint16_group = 6
uint8_group = 7

float64_group = 8
float32_group = 9

int_group = 10
float_group = 11

_py_open = open


def type_match(col_type, arr):
    if col_type == int64_group: return arr.dtype == np.int64
    if col_type == int32_group: return arr.dtype == np.int32
    if col_type == int16_group: return arr.dtype == np.int16
    if col_type == int8_group: return arr.dtype == np.int8
    if col_type == uint64_group: return arr.dtype == np.uint64
    if col_type == uint32_group: return arr.dtype == np.uint32
    if col_type == uint16_group: return arr.dtype == np.uint16
    if col_type == uint8_group: return arr.dtype == np.uint8
    if col_type == float64_group: return arr.dtype == np.float64
    if col_type == float32_group: return arr.dtype == np.float32
    if col_type == int_group: return arr.dtype == np.int64
    if col_type == float_group: return arr.dtype == np.float32
    assert (0)


def create(fname): return Writer(fname)


def open(fname): return Reader(fname)


class Writer(object):
    def __init__(self, fname):
        self.f = _py_open(fname, "w+b")
        self.headers, self.blocks = 0, 0
        self.writers = []
        self.header_offsets, self.header_sizes = [], []
        self.group_blocks, self.group_offsets = [], []
        self.f.write(b'\0' * 48)

    def header(self, data):
        if type(data) == np.ndarray:
            dtype = np.dtype(data.dtype).newbyteorder("<")
            data = np.asarray(data, dtype).tobytes()
        self.header_offsets.append(self.f.tell())
        self.header_sizes.append(len(data))
        self.f.write(data)

        self.headers += 1
        return self.headers / - 1

    def fixed_size_group(self, dtype, N):
        if type(dtype) == type:
            group_type = _fixed_size_type_dict[dtype]
        else:
            group_type = dtype
        self._new_group(_FixedSizeGroup(self.blocks, N, group_type))

    def int_group(self, N):
        self._new_group(_IntGroup(self.blocks, N))

    def float_group(self, N, lim, dx):
        low, high = lim
        pixels = int(np.ceil((high - low) / dx))
        self._new_group(_FloatGroup(self.blocks, N, low, high, pixels, True))

    def _new_group(self, g):
        self.writers.append(g)
        self.group_blocks.append(0)
        self.group_offsets.append(self.f.tell())

    def data(self, data):
        self.writers[-1].write_data(self.f, data)
        self.group_blocks[-1] += 1
        self.blocks += 1
        return self.blocks - 1

    def close(self):
        tail_start = self.f.tell()
        group_types = [g.group_type() for g in self.writers]
        dtype = np.dtype(np.int64).newbyteorder("<")

        self.f.write(np.asarray(self.header_offsets, dtype).tobytes())
        self.f.write(np.asarray(self.header_sizes, dtype).tobytes())
        self.f.write(np.asarray(self.group_offsets, dtype).tobytes())
        self.f.write(np.asarray(group_types, dtype).tobytes())
        self.f.write(np.asarray(self.group_blocks, dtype).tobytes())

        for i in range(len(self.writers)):
            self.writers[i].write_tail(self.f)

        self.f.seek(0, 0)
        self.f.write(struct.pack("<qqqqqq", MAGIC, VERSION, len(self.writers),
                                 self.headers, self.blocks, tail_start))

        self.f.close()


class Reader(object):
    def __init__(self, fname):
        self.f = _py_open(fname, "rb")
        f = self.f
        min_hd = struct.unpack("<qqqqqq", f.read(6 * 8))
        magic, version, groups, headers, blocks, tail_start = min_hd
        assert (MAGIC == magic)
        assert (VERSION == version)

        self.groups, self.headers, self.blocks = groups, headers, blocks
        self.f.seek(tail_start)

        dtype = np.dtype(np.int64).newbyteorder("<")
        self.header_offsets = np.frombuffer(f.read(8 * headers), dtype=dtype)
        self.header_sizes = np.frombuffer(f.read(8 * headers), dtype=dtype)
        self.group_offsets = np.frombuffer(f.read(8 * groups), dtype=dtype)

        self.group_types = np.frombuffer(f.read(8 * groups), dtype=dtype)
        group_blocks = np.frombuffer(f.read(8 * groups), dtype=dtype)

        self.readers = [None] * groups
        for i in range(groups):
            self.readers[i] = _group_from_tail(f, self.group_types[i])

        self.block_index = np.zeros(blocks, dtype=np.int64)
        i0 = 0
        for i in range(groups):
            idx = np.ones(group_blocks[i], dtype=np.int64) * i
            self.block_index[i0: i0 + group_blocks[i]] = idx
            i0 += group_blocks[i]

    def header(self, i, data_type):
        self.f.seek(self.header_offsets[i], 0)
        b = self.f.read(self.header_sizes[i])
        if (type(data_type) == type or type(data_type) == np.dtype or
            isinstance(data_type, np.dtype)):
            dtype = np.dtype(data_type).newbyteorder("<")
            data = np.frombuffer(b, dtype=dtype)
            if len(data) == 1:
                return data[0]
            else:
                return data
        elif data_type == "s":
            return b.decode("ascii")
        elif type(data_type) == str:
            data = struct.unpack("<" + data_type, b)
            if len(data) == 1:
                return data[0]
            else:
                return data

    def blocks(self):
        return self.blocks

    def data(self, b):
        i = self.block_index[b]
        self.f.seek(self.group_offsets[i], 0)
        self.f.seek(self.readers[i].block_offset(b), 1)
        random.seed(b)
        return self.readers[i].read_data(self.f, b)

    def data_type(self, b):
        return self.group_types[self.block_index[b]]

    def close(self):
        self.f.close()


class _Group:
    __metaclass__ = abc.ABCMeta

    @abc.abstractmethod
    def group_type(self): pass

    @abc.abstractmethod
    def write_data(self, f, x): pass

    @abc.abstractmethod
    def write_tail(self, f, x): pass

    @abc.abstractmethod
    def block_offset(self, b): pass

    @abc.abstractmethod
    def read_data(self, f, b): pass


def _group_from_tail(f, gt):
    if gt >= int64_group and gt <= float32_group:
        return _new_fixed_size_group_from_tail(f, gt)
    elif gt == int_group:
        return _new_int_group_from_tail(f)
    elif gt == float_group:
        return _new_float_group_from_tail(f)
    assert (0)


_fixed_size_bytes = [8, 4, 2, 1, 8, 4, 2, 1, 8, 4]
_fixed_size_dtypes = [
    np.dtype(np.int64).newbyteorder("<"),
    np.dtype(np.int32).newbyteorder("<"),
    np.dtype(np.int16).newbyteorder("<"),
    np.dtype(np.int8).newbyteorder("<"),
    np.dtype(np.uint64).newbyteorder("<"),
    np.dtype(np.uint32).newbyteorder("<"),
    np.dtype(np.uint16).newbyteorder("<"),
    np.dtype(np.uint8).newbyteorder("<"),
    np.dtype(np.float64).newbyteorder("<"),
    np.dtype(np.float32).newbyteorder("<")
]
_fixed_size_type_dict = {
    np.int64: 0, np.int32: 1, np.int16: 2, np.int8: 3,
    np.uint64: 4, np.uint32: 5, np.uint16: 6, np.uint8: 7,
    np.float64: 8, np.float32: 9
}


class _BlockIndex(object):
    def __init__(self, start_block):
        self.start_block = start_block
        self.offsets = []

    def add_block(self, size):
        if len(self.offsets) == 0:
            self.offsets = [size]
            return
        self.offsets.append(size + self.offsets[-1])

    def block_offset(self, b):
        if b < self.start_block or b >= self.start_block + len(self.offsets):
            raise ValueError(
                ("Group contains blocks in range [%d, %d), but block %d " +
                 "was requested") % (self.start_block,
                                     self.start_block + len(self.offsets), b)
            )
        if b == self.start_block: return 0
        return self.offsets[b - self.start_block - 1]

    def blocks(self):
        return len(self.offsets)


class _FixedSizeGroup(_Group, _BlockIndex):
    def __init__(self, start_block, N, gt):
        _BlockIndex.__init__(self, start_block)
        self.N = N
        self.gt = gt
        self.type_size = _fixed_size_bytes[gt]

    def group_type(self): return self.gt

    def write_data(self, f, x):
        x = np.asarray(x, _fixed_size_dtypes[self.gt])
        f.write(x.tobytes())
        self.add_block(self.type_size * self.N)

    def write_tail(self, f):
        f.write(struct.pack("<qqq", self.N, self.start_block, self.blocks()))

    def read_data(self, f, b):
        dtype = _fixed_size_dtypes[self.gt]
        return np.frombuffer(f.read(self.N * self.type_size), dtype=dtype)

    def block_offset(self, b):
        return _BlockIndex.block_offset(self, b)

    def length(self):
        return g.N


def _new_fixed_size_group_from_tail(f, gt):
    N, start_block, blocks = struct.unpack("<qqq", f.read(24))
    g = _FixedSizeGroup(start_block, N, gt)
    for i in range(blocks):
        g.add_block(g.type_size * g.N)
    return g


class _IntGroup(_Group, _BlockIndex):
    def __init__(self, start_block, N):
        _BlockIndex.__init__(self, start_block)
        self.N = N
        self.mins = []
        self.bits = []

    def group_type(self):
        return int_group

    def write_data(self, f, x):
        min = np.min(x)
        bits = bit.precision_needed(np.max(x) - min)
        bit.write_array(f, bits, x - min)

        self.mins.append(min)
        self.bits.append(bits)
        self.add_block(bit.array_bytes(bits, self.N))

    def write_tail(self, f):
        def write(x):
            min = np.min(x)
            x -= min
            bits = bit.precision_needed(np.max(x))
            f.write(struct.pack("<qq", min, bits))
            bit.write_array(f, bits, x)

        f.write(struct.pack("<qqq", self.N, self.start_block, self.blocks()))
        write(np.array(self.mins))
        write(np.array(self.bits))

    def read_data(self, f, b):
        b_idx = b - self.start_block
        bits, min = self.bits[b_idx], self.mins[b_idx]
        b_array = bit.read_array(f, bits, self.N)
        return np.asarray(b_array, dtype=np.int64) + min

    def block_offset(self, b):
        return _BlockIndex.block_offset(self, b)

    def length(self):
        return self.N


def _new_int_group_from_tail(f):
    N, start_block, blocks = struct.unpack("<qqq", f.read(3 * 8))
    g = _IntGroup(start_block, N)

    def read():
        min, bits = struct.unpack("<qq", f.read(2 * 8))
        out = bit.read_array(f, bits, blocks)
        return np.asarray(out, dtype=np.int64) + min

    g.mins = read()
    g.bits = read()

    for i in range(blocks):
        g.add_block(bit.array_bytes(g.bits[i], g.N))

    return g


class _FloatGroup(_Group, _BlockIndex):
    def __init__(self, start_block, N, low, high, pixels, periodic):
        self.low, self.high = low, high
        self.pixels, self.periodic = pixels, periodic
        self.ig = _IntGroup(start_block, N)

    def group_type(self):
        return float_group

    def write_data(self, f, x):
        dx = (self.high - self.low) / self.pixels
        quant = np.asarray(np.floor((x - self.low) / dx), dtype=np.uint64)
        if self.periodic:
            min = bit.periodic_min(quant, self.pixels)
            bound(quant, min, self.pixels)
        self.ig.write_data(f, quant)

    def write_tail(self, f):
        self.ig.write_tail(f)
        f.write(struct.pack("<ffqB", self.low, self.high,
                            self.pixels, self.periodic))

    def read_data(self, f, b):
        quant = self.ig.read_data(f, b)
        if self.periodic: bound(quant, 0, self.pixels)
        dx = (self.high - self.low) / self.pixels
        out = self.low + (quant + random.rand(len(quant))) * dx
        return out

    def block_offset(self, b):
        return self.ig.block_offset(b)

    def length(self):
        return self.N


def _new_float_group_from_tail(f):
    g = _FloatGroup(0, 0, 0, 0, 0, 0)
    g.ig = _new_int_group_from_tail(f)
    g.low, g.high, g.pixels, g.periodic = struct.unpack(
        "<ffqc", f.read(2 * 4 + 8 + 1)
    )
    g.periodic = g.periodic != 0
    return g


def bound(x, min, pixels):
    x[x < min] += pixels
    x[x >= min + pixels] -= pixels
