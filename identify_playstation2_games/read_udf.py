#!/usr/bin/env python
# -*- coding: UTF-8 -*-

# Copyright (c) 2015, Matthew Brennan Jones <matthew.brennan.jones@gmail.com>
# Copyright (c) 2008-2011, Kenneth Bell https://discutils.codeplex.com
# A module for reading DVD ISOs (Universal Disk Format) with Python 2 & 3
# It uses a MIT style license
# It is hosted at: https://github.com/workhorsy/py-read-udf
#
# See ECMA-167 and OSTA Universal Disk Format for details:
# http://en.wikipedia.org/wiki/Universal_Disk_Format
# https://sites.google.com/site/udfintro/
# http://www.ecma-international.org/publications/files/ECMA-ST/Ecma-167.pdf
# http://www.osta.org/specs/pdf/udf260.pdf
# 
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
# 
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
# CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.


import sys, os
import struct

IS_PY2 = sys.version_info[0] == 2

MAX_INT = 2 ** (struct.Struct('i').size * 8 - 1) - 1
HEADER_SIZE = 1024 * 32
SECTOR_SIZE = 1024 * 2 # FIXME: This should not be hard coded


def to_uint8(buffer, start = 0):
	return struct.unpack('B', buffer[start : start + 1])[0]

def to_uint16(buffer, start = 0):
	left = ((to_uint8(buffer, start + 1) << 8) & 0xFF00)
	right = ((to_uint8(buffer, start + 0) << 0) & 0x00FF)
	return (left | right)

def to_uint32(buffer, start = 0):
	a = ((to_uint8(buffer, start + 3) << 24) & 0xFF000000)
	b = ((to_uint8(buffer, start + 2) << 16) & 0x00FF0000)
	c = ((to_uint8(buffer, start + 1) << 8) & 0x0000FF00)
	d = ((to_uint8(buffer, start + 0) << 0) & 0x000000FF)
	return(a | b | c | d)

def to_uint64(buffer, start = 0):
	a = ((to_uint8(buffer, start + 7) << 56) & 0xFF00000000000000)
	b = ((to_uint8(buffer, start + 6) << 48) & 0x00FF000000000000)
	c = ((to_uint8(buffer, start + 5) << 40) & 0x0000FF0000000000)
	d = ((to_uint8(buffer, start + 4) << 32) & 0x000000FF00000000)
	e = ((to_uint8(buffer, start + 3) << 24) & 0x00000000FF000000)
	f = ((to_uint8(buffer, start + 2) << 16) & 0x0000000000FF0000)
	g = ((to_uint8(buffer, start + 1) << 8) & 0x000000000000FF00)
	h = ((to_uint8(buffer, start + 0) << 0) & 0x00000000000000FF)
	return(a | b | c | d | e | f | g | h)

def round_up(value, unit):
	return ((value + (unit - 1)) // unit) * unit

def to_dstring(buffer, offset, count):
	byte_len = to_uint8(buffer, offset + count - 1)
	return to_dchars(buffer, offset, byte_len)

def to_dchars(buffer, offset, count):
	if count == 0:
		return b""

	alg = to_uint8(buffer, offset)

	if alg not in [8, 16]:
		raise Exception("Corrupt compressed unicode string")

	result = []

	pos = 1
	while pos < count:
		ch = to_uint8(b"\0")

		if alg == 16:
			ch = (to_uint8(buffer, offset + pos) << 8)
			pos += 1

		if pos < count:
			ch |= to_uint8(buffer, offset + pos)
			pos += 1

		result.append(ch)

	# Convert from ints to chars
	if IS_PY2:
		result = [bytes(chr(n)) for n in result]
	else:
		result = [bytes(chr(n), 'utf-8') for n in result]

	return b''.join(result)


class BaseTag(object):
	def __init__(self, size, buffer, start):
		self._size = size

		self._assert_size(buffer, start)

	def get_size(self):
		return self._size
	size = property(get_size)

	# Make sure there is enough space
	def _assert_size(self, buffer, start):
		# Just return if the size is zero
		if self._size == 0:
			return

		if len(buffer) - start < self._size:
			raise Exception("{0} requires {1} bytes, but buffer only has {2}".format(type(self), self._size, len(buffer) - start))

	# Make sure the checksums match
	def _assert_checksum(self, buffer, start, expected_checksum):
		checksum = 0
		for i in range(16):
			if i == 4:
				continue

			checksum += to_uint8(buffer, start + i)

		# Truncate int to uint8
		b = checksum
		while checksum >= 256:
			checksum -= 256

		if not checksum == expected_checksum:
			raise Exception("Checksum was {0}, but {1} was expected".format(checksum, expected_checksum))

	# Make sure it is the correct type of tag
	def _assert_tag_identifier(self, expected_tag_identifier):
		if not self.descriptor_tag.tag_identifier == expected_tag_identifier:
			raise Exception("Expected Tag Identifier {0}, but was {1}".format(expected_tag_identifier, self.descriptor_tag.tag_identifier))

	# Make sure the reserved space is all zeros
	def _assert_reserve_space(self, buffer, start, length):
		buf_seg = buffer[start : start + length]
		for i in range(len(buf_seg)):
			n = buf_seg[i : i + 1]
			if not to_uint8(n) == 0:
				raise Exception("Reserve space at {0} was not zero.".format(start))


class UdfContext(object):
	def __init__(self, file, physical_sector_size):
		self.file = file
		self.logical_partitions = []
		self.physical_partitions = {}
		self.physical_sector_size = physical_sector_size


# "2.1.5 Entity Identifier" of http://www.osta.org/specs/pdf/udf260.pdf
class EntityIdType(object): # enum
	unknown = 0
	DomainIdentifier = 1
	UDFIdentifier = 2
	ImplementationIdentifier = 3
	ApplicationIdentifier = 4


# page 14 of http://www.osta.org/specs/pdf/udf260.pdf
# 1/12 of http://www.ecma-international.org/publications/files/ECMA-ST/Ecma-167.pdf
class EntityID(BaseTag):
	def __init__(self, entity_id_type, buffer, start):
		super(EntityID, self).__init__(32, buffer, start)

		self.entity_id_type = entity_id_type
		self.flags = to_uint8(buffer, start + 0)
		self.identifier = buffer[start + 1 : start + 24]
		self.identifier_suffix = buffer[start + 24 : start + 32]

		# Make sure the flag is always 0
		#if self.flags != 0:
		#	raise Exception("EntityID flags was not zero")


# page 3/4 of http://www.ecma-international.org/publications/files/ECMA-ST/Ecma-167.pdf
# page 4/4 of http://www.ecma-international.org/publications/files/ECMA-ST/Ecma-167.pdf
class TagIdentifier(object): # enum
	unknown = 0
	PrimaryVolumeDescriptor = 1
	AnchorVolumeDescriptorPointer = 2
	VolumeDescriptorPointer = 3
	ImplementationUseVolumeDescriptor = 4
	PartitionDescriptor = 5
	LogicalVolumeDescriptor = 6
	UnallocatedSpaceDescriptor = 7
	TerminatingDescriptor = 8
	LogicalVolumeIntegrityDescriptor = 9
	FileSetDescriptor = 256
	FileIdentifierDescriptor = 257
	FileEntry = 261


# page 3/3 of http://www.ecma-international.org/publications/files/ECMA-ST/Ecma-167.pdf
# page 20 of http://www.osta.org/specs/pdf/udf260.pdf
class DescriptorTag(BaseTag):
	def __init__(self, buffer, start = 0):
		super(DescriptorTag, self).__init__(16, buffer, start)

		self.tag_identifier = to_uint16(buffer, start + 0)
		self.descriptor_version = to_uint16(buffer, start + 2)
		self.tag_check_sum = to_uint8(buffer, start + 4)
		self.reserved = to_uint8(buffer, start + 5)
		self.tag_serial_number = to_uint16(buffer, start + 6)
		self.descriptor_crc = to_uint16(buffer, start + 8)
		self.descriptor_crc_length = to_uint16(buffer, start + 10)
		self.tag_location = to_uint32(buffer, start + 12)

		# Make sure the identifier is known
		if self.tag_identifier == TagIdentifier.unknown:
			raise Exception("Tag Identifier was unknown")

		self._assert_checksum(buffer, start, self.tag_check_sum)
		self._assert_reserve_space(buffer, start + 5, 1)


# page 3/3 of http://www.ecma-international.org/publications/files/ECMA-ST/Ecma-167.pdf
class ExtentDescriptor(BaseTag):
	def __init__(self, buffer, start = 0):
		super(ExtentDescriptor, self).__init__(8, buffer, start)

		self.extent_length = to_uint32(buffer, start)
		self.extent_location = to_uint32(buffer, start + 4)


# page 3/15 of http://www.ecma-international.org/publications/files/ECMA-ST/Ecma-167.pdf
class AnchorVolumeDescriptorPointer(BaseTag):
	def __init__(self, buffer, start = 0):
		super(AnchorVolumeDescriptorPointer, self).__init__(512, buffer, start)

		self.descriptor_tag = DescriptorTag(buffer, start)
		self._assert_tag_identifier(TagIdentifier.AnchorVolumeDescriptorPointer)

		self.main_volume_descriptor_sequence_extent = ExtentDescriptor(buffer, start + 16)
		self.reserve_volume_descriptor_sequence_extent = ExtentDescriptor(buffer, start + 24)
		self.reserved = buffer[start + 32 : start + 512]

		self._assert_reserve_space(buffer, start + 32, 480)


class PhysicalPartition(object):
	def __init__(self, file, start, length):
		self._file = file
		self._start = start
		self._length = length


class LogicalPartition(object):
	def __init__(self, context, volume_descriptor):
		self.context = context
		self.volume_descriptor = volume_descriptor

	def get_logical_block_size(self):
		return self._volume_descriptor.logical_block_size
	logical_block_size = property(get_logical_block_size)

	@classmethod
	def from_descriptor(cls, context, volume_descriptor, index):
		map = volume_descriptor.partition_maps[index]
		if isinstance(map, Type1PartitionMap):
			return Type1Partition(context, volume_descriptor, map)
		else:
			raise NotImplementedError("Unrecognised type of partition map {0}".format(type(map)))


class Type1Partition(LogicalPartition):
	def __init__(self, context, volume_descriptor, partition_map):
		super(Type1Partition, self).__init__(context, volume_descriptor)
		self.partition_map = partition_map
		self.physical_partition = context.physical_partitions[partition_map.partition_number]

	def get_logical_block_size(self):
		return self.volume_descriptor.logical_block_size
	logical_block_size = property(get_logical_block_size)


# page 4/17 of http://www.ecma-international.org/publications/files/ECMA-ST/Ecma-167.pdf
class FileSetDescriptor(BaseTag):
	def __init__(self, buffer, start = 0):
		super(FileSetDescriptor, self).__init__(512, buffer, start)

		self.descriptor_tag = DescriptorTag(buffer, start)
		self._assert_tag_identifier(TagIdentifier.FileSetDescriptor)

		self.recording_date_and_time = buffer[start + 16 : start + 28] # FIXME: timestamp
		self.interchange_level = to_uint16(buffer, start + 28)
		self.maximum_interchange_level = to_uint16(buffer, start + 30)
		self.character_set_list = to_uint32(buffer, start + 32)
		self.maximum_character_set_list = to_uint32(buffer, start + 36)
		self.file_set_number = to_uint32(buffer, start + 40)
		self.file_set_descriptor_number = to_uint32(buffer, start + 44)
		self.logical_volume_identifier_character_set = buffer[start + 48 : start + 112] # FIXME: charspec
		self.logical_volume_identifier = to_dstring(buffer, start + 112, 128)
		self.file_set_character_set = buffer[start + 240 : start + 274] # FIXME: charspec
		self.file_set_identifier = to_dstring(buffer, start + 304, 32)
		self.copyright_file_identifier = to_dstring(buffer, start + 336, 32)
		self.abstract_file_identifier = to_dstring(buffer, start + 368, 32)
		self.root_directory_icb = LongAllocationDescriptor(buffer, start + 400)
		self.domain_identifier = EntityID(EntityIdType.DomainIdentifier, buffer, start + 416)
		self.next_extent = LongAllocationDescriptor(buffer, start + 448)
		self.system_stream_directory_icb = LongAllocationDescriptor(buffer, start + 464)
		self.reserved = buffer[start + 480 : start + 512]

		self._assert_reserve_space(buffer, start + 480, 32)


# page 3/12 of http://www.ecma-international.org/publications/files/ECMA-ST/Ecma-167.pdf
class PrimaryVolumeDescriptor(BaseTag):
	def __init__(self, buffer, start = 0):
		super(PrimaryVolumeDescriptor, self).__init__(512, buffer, start)

		self.descriptor_tag = DescriptorTag(buffer, start)
		self._assert_tag_identifier(TagIdentifier.PrimaryVolumeDescriptor)

		self.volume_descriptor_sequence_number = to_uint32(buffer, start + 16)
		self.primary_volume_descriptor_number = to_uint32(buffer, start + 20)
		self.volume_identifier = to_dstring(buffer, start + 24, 32)
		self.volume_sequence_number = to_uint16(buffer, start + 56)
		self.maximum_volume_sequence_number = to_uint16(buffer, start + 58)
		self.interchange_level = to_uint16(buffer, start + 60)
		self.maximum_interchange_level = to_uint16(buffer, start + 62)
		self.character_set_list = to_uint32(buffer, start + 64)
		self.maximum_character_set_list = to_uint32(buffer, start + 68)
		self.volume_set_identifier = to_dstring(buffer, start + 72, 128)
		self.descriptor_character_set = buffer[start + 200 : start + 264] # FIXME: char spec
		self.expalnatory_character_set = buffer[start + 264 : start + 328] # FIXME: char spec
		self.volume_abstract = ExtentDescriptor(buffer, start + 328)
		self.volume_copyright_notice = ExtentDescriptor(buffer, start + 336)
		self.application_identifier = EntityID(EntityIdType.ApplicationIdentifier, buffer, start + 344)
		self.recording_date_and_time = buffer[start + 376 : start + 388] # FIXME: timestamp
		self.implementation_identifier = EntityID(EntityIdType.ImplementationIdentifier, buffer, start + 388)
		self.implementation_use = buffer[start + 420 : start + 484]
		self.predecessor_volume_descriptor_sequence_location = to_uint32(buffer, start + 484)
		self.flags = to_uint16(buffer, start + 488)
		self.reserved = buffer[start + 490 : start + 512]

		self._assert_reserve_space(buffer, start + 490, 22)


# page 3/17 of http://www.ecma-international.org/publications/files/ECMA-ST/Ecma-167.pdf
# page 45 of http://www.osta.org/specs/pdf/udf260.pdf
class PartitionDescriptor(BaseTag):
	def __init__(self, buffer, start = 0):
		super(PartitionDescriptor, self).__init__(512, buffer, start)

		self.descriptor_tag = DescriptorTag(buffer, start)
		self._assert_tag_identifier(TagIdentifier.PartitionDescriptor)

		self.volume_descriptor_sequence_number = to_uint32(buffer, start + 16)
		self.partition_flags = to_uint16(buffer, start + 20)
		self.partition_number = to_uint16(buffer, start + 22)
		self.partition_contents = EntityID(EntityIdType.UDFIdentifier, buffer, start + 24)
		self.partition_contents_use = buffer[start + 56 : start + 184]
		self.access_type = to_uint32(buffer, start + 184)
		self.partition_starting_location = to_uint32(buffer, start + 188)
		self.partition_length = to_uint32(buffer, start + 192)
		self.implementation_identifier = EntityID(EntityIdType.ImplementationIdentifier, buffer, start + 196)
		self.implementation_use = buffer[start + 228 : start + 356]
		self.reserved = buffer[start + 356 : start + 512]

		# If the partition has allocated volume space
		if self.partition_flags == 1:
			pass

		self._assert_reserve_space(buffer, start + 356, 156)


# page 3/19 of http://www.ecma-international.org/publications/files/ECMA-ST/Ecma-167.pdf
# page 24 of http://www.osta.org/specs/pdf/udf260.pdf
class LogicalVolumeDescriptor(BaseTag):
	def __init__(self, buffer, start = 0):
		super(LogicalVolumeDescriptor, self).__init__(512, buffer, start)

		self.descriptor_tag = DescriptorTag(buffer, start)
		self._assert_tag_identifier(TagIdentifier.LogicalVolumeDescriptor)

		self.volume_descriptor_sequence_number = to_uint32(buffer, start + 16)
		self.descriptor_character_set = buffer[start + 20 : start + 84] # FIXME: charspec
		self.logical_volume_identifier = to_dstring(buffer, start + 84, 128)
		self.logical_block_size = to_uint32(buffer, start + 212)
		self.domain_identifier = EntityID(EntityIdType.DomainIdentifier, buffer, start + 216)
		self.logical_volume_contents_use = buffer[start + 248 : start + 264]
		self.map_table_length = to_uint32(buffer, start + 264)
		self.number_of_partition_maps = to_uint32(buffer, start + 268)
		self.implementation_identifier = EntityID(EntityIdType.ImplementationIdentifier, buffer, start + 272)
		self.implementation_use = buffer[start + 304 : start + 432]
		self.integrity_sequence_extent = ExtentDescriptor(buffer, start + 432)
		self._raw_partition_maps = buffer[start + 440 : start + 512]

		if not b"*OSTA UDF Compliant" in self.domain_identifier.identifier:
			raise Exception("Logical Volume is not OSTA compliant")

	# "10.6.13 Partition Maps (BP 440)" of http://www.ecma-international.org/publications/files/ECMA-ST/Ecma-167.pdf
	def get_partition_maps(self):
		buffer = self._raw_partition_maps
		retval = []
		part_start = 0
		for i in range(self.number_of_partition_maps):
			partition_type = to_uint8(buffer, part_start)
			partitioin = None
			if partition_type == 1:
				partition = Type1PartitionMap(buffer, part_start)
			else:
				raise Exception("Unexpected partition type {0}".format(partition_type))

			retval.append(partition)
			part_start += partition.size

		return retval
	partition_maps = property(get_partition_maps)

	# "2.2.4.4 byte LogicalVolumeContentsUse[16]" of http://www.osta.org/specs/pdf/udf260.pdf
	def get_file_set_descriptor_location(self):
		return LongAllocationDescriptor(self.logical_volume_contents_use)
	file_set_descriptor_location = property(get_file_set_descriptor_location)


# page 60 of http://www.osta.org/specs/pdf/udf260.pdf
class LongAllocationDescriptor(BaseTag):
	def __init__(self, buffer, start = 0):
		super(LongAllocationDescriptor, self).__init__(16, buffer, start)

		self.extent_length = to_uint32(buffer, start + 0)
		self.extent_location = LogicalBlockAddress(buffer, start + 4)
		self.implementation_use = buffer[start + 10 : start + 16]


# page 4/3 of http://www.ecma-international.org/publications/files/ECMA-ST/Ecma-167.pdf
class LogicalBlockAddress(BaseTag):
	def __init__(self, buffer, start = 0):
		super(LogicalBlockAddress, self).__init__(6, buffer, start)
		self.logical_block_number = to_uint32(buffer, start + 0)
		self.partition_reference_number = to_uint16(buffer, start + 4)


class TerminatingDescriptor(BaseTag):
	def __init__(self, buffer, start = 0):
		super(TerminatingDescriptor, self).__init__(512, buffer, start)

	# FIXME: Add the rest


# page 3/21 of http://www.ecma-international.org/publications/files/ECMA-ST/Ecma-167.pdf
class Type1PartitionMap(BaseTag):
	def __init__(self, buffer, start):
		super(Type1PartitionMap, self).__init__(6, buffer, start)

		self.partition_map_type = to_uint8(buffer, start + 0)
		self.partition_map_length = to_uint8(buffer, start + 1)
		self.volume_sequence_number = to_uint16(buffer, start + 2)
		self.partition_number = to_uint16(buffer, start + 4)

		if not self.partition_map_type == 1:
			raise Exception("Type 1 Partition Map Type was {0} instead of 1.".format(self.partition_map_type))

		if not self.partition_map_length == self.size:
			raise Exception("Type 1 Partition Map Length was {0} instead of {1}.".format(self.partition_map_length, self.size))


# page 3/22 of http://www.ecma-international.org/publications/files/ECMA-ST/Ecma-167.pdf
class Type2PartitionMap(BaseTag):
	def __init__(self, buffer, start):
		super(Type2PartitionMap, self).__init__(64, buffer, start)

		self.partition_map_type = to_uint8(buffer, start + 0)
		self.partition_map_length = to_uint8(buffer, start + 1)
		self.partition_type_identifier = EntityID(EntityIdType.UDFIdentifier, start + 4, start + 32)

		if not self.partition_map_type == 2:
			raise Exception("Type 2 Partition Map Type was {0} instead of 2.".format(self.partition_map_type))

		if not self.partition_map_length == self.size:
			raise Exception("Type 2 Partition Map Length was {0} instead of {1}.".format(self.partition_map_length, self.size))


# page 4/28 of http://www.ecma-international.org/publications/files/ECMA-ST/Ecma-167.pdf
# page 56 of http://www.osta.org/specs/pdf/udf260.pdf
class FileEntry(BaseTag):
	def __init__(self, buffer, start = 0):
		super(FileEntry, self).__init__(300, buffer, start) # FIXME: How do we deal with this having a dynamic size?

		self.descriptor_tag = DescriptorTag(buffer, start)
		self._assert_tag_identifier(TagIdentifier.FileEntry)

		self.icb_tag = ICBTag(buffer, start + 16)
		self.uid = to_uint32(buffer, start + 36)
		self.gid = to_uint32(buffer, start + 40)
		self.permissions = to_uint32(buffer, start + 44)
		self.file_link_count = to_uint16(buffer, start + 48)
		self.record_format = to_uint8(buffer, start + 50)
		self.record_display_attributes = to_uint8(buffer, start + 51)
		self.record_length = to_uint32(buffer, start + 52)
		self.information_length = to_uint64(buffer, start + 56)
		self.logical_blocks_recorded = to_uint64(buffer, start + 64)
		self.access_date_and_time = buffer[start + 72 : start + 84] # FIXME: timestamp
		self.modification_date_and_time = buffer[start + 84 : start + 96] # FIXME: timestamp
		self.attribute_date_and_time = buffer[start + 96 : start + 108] # FIXME: timestamp
		self.checkpoint = to_uint32(buffer, start + 108)
		self.extended_attribute_icb = LongAllocationDescriptor(buffer, start + 112)
		self.implementation_identifier = EntityID(EntityIdType.ImplementationIdentifier, buffer, start + 128)
		self.uinque_id = to_uint64(buffer, start + 160)
		self.length_of_extended_attributes = to_uint32(buffer, start + 168)
		self.length_of_allocation_descriptors = to_uint32(buffer, start + 173)
		self.extended_attributes = buffer[start + 176 : start + 176 + self.length_of_extended_attributes]
		self.allocation_descriptors = buffer[start + 176 + self.length_of_extended_attributes : start + 176 + self.length_of_extended_attributes + self.length_of_allocation_descriptors]


# page 4/25 of http://www.ecma-international.org/publications/files/ECMA-ST/Ecma-167.pdf
class FileType(object): # enum
	unknown = 0
	unallocated_space_entry = 1
	partition_integrity_entry = 2
	indirect_entry = 3
	directory = 4
	sequence_of_bytes = 5
	block_special_device_file = 6
	character_special_device_file = 7
	recording_extended_attributes = 8
	fifo = 9
	c_issock = 10
	terminal_entry = 11
	symbolic_link = 12
	stream_directory = 13


# page 4/23 of http://www.ecma-international.org/publications/files/ECMA-ST/Ecma-167.pdf
# "2.3.5 ICB Tag" of http://www.osta.org/specs/pdf/udf260.pdf
class ICBTag(BaseTag):
	def __init__(self, buffer, start = 0):
		super(ICBTag, self).__init__(20, buffer, start)

		self.prior_recorded_number_of_direct_entries = to_uint32(buffer, start)
		self.strategy_type = to_uint16(buffer, start + 4)
		self.strategy_parameter = buffer[start + 6 : start + 2]
		self.maximum_number_of_entries = to_uint16(buffer, start + 8)
		self.reserved = buffer[start + 10: start + 11]
		self.file_type = to_uint8(buffer, start + 11)
		self.parent_icb_location = LogicalBlockAddress(buffer, start + 12)
		raw_flags = to_uint16(buffer, start + 18)
		self.allocation_type = raw_flags & 0x3
		self.flags = raw_flags & 0xFFFC

		self._assert_reserve_space(buffer, start + 10, 1)


class CookedExtent(object):
	def __init__(self, file_content_offset, partition, start_pos, length):
		self.file_content_offset = file_content_offset
		self.partition = partition
		self.start_pos = start_pos
		self.length = length


class ShortAllocationDescriptor(BaseTag):
	def __init__(self, buffer, start = 0):
		super(ShortAllocationDescriptor, self).__init__(8, buffer, start)
		length = to_uint32(buffer, start)
		self.extent_location = to_uint32(buffer, start + 4)
		self.extent_length = length & 0x3FFFFFFF
		self.flags = (length >> 30) & 0x3


class AllocationType(object): # enum
	short_descriptors = 0
	long_descriptors = 1
	extended_descriptors = 2
	embedded = 3


class FileContentBuffer(object):
	def __init__(self, context, partition, file_entry, block_size):
		self.context = context
		self.partition = partition
		self.file_entry = file_entry
		self.block_size = block_size
		self.extents = None

		self.load_extents()

	def load_extents(self):
		self.extents = []
		active_buffer = self.file_entry.allocation_descriptors

		# Short descriptors
		alloc_type = self.file_entry.icb_tag.allocation_type
		if alloc_type == AllocationType.short_descriptors:
			file_pos = 0
			i = 0
			while i < len(active_buffer):
				sad = ShortAllocationDescriptor(active_buffer, i)
				if sad.extent_length == 0:
					break
				if sad.flags != 0:
					raise NotImplementedError("Can't use extents that are not recorded and allocated.")

				new_extent = CookedExtent(file_pos, MAX_INT, sad.extent_location * self.block_size, sad.extent_length)
				self.extents.append(new_extent)
				file_pos += sad.extent_length
				i += sad.size
		elif alloc_type == AllocationType.embedded:
			raise NotImplementedError()
		elif alloc_type == AllocationType.long_descriptors:
			raise NotImplementedError()
		else:
			raise NotImplementedError("FIXME: Add support for allocation type {0}".format(alloc_type))

	def get_capacity(self):
		return self.file_entry.information_length
	capacity = property(get_capacity)

	def read(self, pos, offset, count):
		buffer = []
		if self.file_entry.icb_tag.allocation_type == AllocationType.embedded:
			src_buffer = self.file_entry.allocation_descriptors
			if pos > len(src_buffer):
				return buffer

			to_copy = min(len(src_buffer) - pos, count)
			buffer[offset : offset + to_copy] = src_buffer[pos : pos + to_copy]
			return buffer
		else:
			return self.read_from_extents(pos, offset, count)

	def read_from_extents(self, pos, offset, count):
		total_to_read = min(self.capacity - pos, count)
		total_read = 0
		buffer = []

		while total_read < total_to_read:
			extent = self.find_extent(pos + total_read)

			extent_offset = (pos + total_read) - extent.file_content_offset
			to_read = min(total_to_read - total_read, extent.length - extent_offset)

			part = None
			if extent.partition != MAX_INT:
				part = self.logical_partitions[extent.partition]
			else:
				part = self.partition

			new_pos = extent.start_pos + extent_offset + part.physical_partition._start
			part.physical_partition._file.seek(new_pos)
			buffer = part.physical_partition._file.read(to_read)
			if len(buffer) == 0:
				return buffer

			total_read += len(buffer)

		return buffer

	def find_extent(self, pos):
		for extent in self.extents:
			if extent.file_content_offset + extent.length > pos:
				return extent

		return None


class File(object):
	def __init__(self, context, partition, file_entry, block_size):
		self.context = context
		self.partition = partition
		self.file_entry = file_entry
		self.block_size = block_size
		self.content = None

	@classmethod
	def from_descriptor(cls, context, icb):
		partition = context.logical_partitions[icb.extent_location.partition_reference_number]
		root_data_dir = read_extent(context, icb)

		dt = DescriptorTag(root_data_dir)
		if dt.tag_identifier == TagIdentifier.FileEntry:
			file_entry = FileEntry(root_data_dir)
			if file_entry.icb_tag.file_type == FileType.directory:
				return Directory(context, partition, file_entry)
			else:
				raise NotImplementedError("FIXME: Expected a directory not a FileType of {0}".format(file_entry.icb_tag.file_type))
		else:
			raise NotImplementedError("FIXME: Add the code for handling Tag Identifier {0}".format(dt.tag_identifier))

	def get_file_content(self):
		if self.content:
			return self.content

		self.content = FileContentBuffer(self.context, self.partition, self.file_entry, self.block_size)
		return self.content
	file_content = property(get_file_content)


class FileCharacteristic(object): # enum
	existence = 0x01
	directory = 0x02
	deleted = 0x04
	parent = 0x08
	metadata = 0x10


# page 4/21 of http://www.ecma-international.org/publications/files/ECMA-ST/Ecma-167.pdf
class FileIdentifierDescriptor(BaseTag):
	def __init__(self, buffer, start = 0):
		super(FileIdentifierDescriptor, self).__init__(0, buffer, start)

		self.rounded_size = 0

		self.descriptor_tag = DescriptorTag(buffer, start)
		self._assert_tag_identifier(TagIdentifier.FileIdentifierDescriptor)

		self.file_version_number = to_uint16(buffer, start + 16)
		self.file_characteristics = to_uint8(buffer, start + 18)
		self.length_of_file_identifier = to_uint8(buffer, start + 19)
		self.ICB = LongAllocationDescriptor(buffer, start + 20)
		self.length_of_implementation_use = to_uint16(buffer, start + 36)
		self.implementation_use = buffer[start + 38 : start + 38 + self.length_of_implementation_use]

		s = start + 38 + self.length_of_implementation_use
		l = self.length_of_file_identifier
		self.file_identifier = to_dchars(buffer, s, l)

		self.rounded_size = round_up(38 + self.length_of_implementation_use + self.length_of_file_identifier, 4)


class Directory(File):
	def __init__(self, context, partition, file_entry):
		super(Directory, self).__init__(context, partition, file_entry, partition.logical_block_size)
		if self.file_content.capacity > MAX_INT:
			raise NotImplementedError("Directory too big")

		self._entries = []
		content_bytes = self.file_content.read(0, 0, self.file_content.capacity)

		pos = 0
		while pos < len(content_bytes):
			id = FileIdentifierDescriptor(content_bytes, int(pos))

			if (id.file_characteristics & (FileCharacteristic.deleted | FileCharacteristic.parent)) == 0:
				self._entries.append(id)

			pos += id.rounded_size

	def get_all_entries(self):
		return self._entries
	all_entries = property(get_all_entries)


def read_extent(context, extent):
	partition = context.logical_partitions[extent.extent_location.partition_reference_number]
	offset = partition.physical_partition._start
	pos = extent.extent_location.logical_block_number * partition.logical_block_size
	length = extent.extent_length
	context.file.seek(offset + pos)
	retval = context.file.read(length)
	return retval


# FIXME: This assumes the sector size is 2048
def is_valid_udf(file, file_size):
	# Move to the start of the file
	file.seek(0)

	# Make sure there is enough space for a header and sector
	if file_size < HEADER_SIZE + SECTOR_SIZE:
		return False

	# Move past 32K of empty space
	file.seek(HEADER_SIZE)

	is_valid = True
	has_bea, has_vsd, has_tea = False, False, False

	# Look at each sector
	while(is_valid):
		# Read the next sector
		buffer = file.read(SECTOR_SIZE)
		if len(buffer) < SECTOR_SIZE:
			break

		# Get the sector meta data
		structure_type = to_uint8(buffer, 0)
		standard_identifier = buffer[1 : 6]
		structure_version = to_uint8(buffer, 6)

		# Check if we have the beginning, middle, or end
		if standard_identifier in [b'BEA01']:
			has_bea = True
		elif standard_identifier in [b'NSR02', b'NSR03']:
			has_vsd = True
		elif standard_identifier in [b'TEA01']:
			has_tea = True
		elif standard_identifier in [b'BOOT2', b'CD001', b'CDW02']:
			pass
		else:
			is_valid = False

	return has_bea and has_vsd and has_tea


def get_sector_size(file, file_size):
	sizes = [4096, 2048, 1024, 512]
	for size in sizes:
		# Skip this size if the file is too small for all the sectors
		if file_size < 257 * size:
			continue

		# Move to the last sector
		file.seek(256 * size)

		# Read the Descriptor Tag
		buffer = file.read(16)
		tag = None
		try:
			tag = DescriptorTag(buffer)
		# Skip if the tag is not valid
		except:
			continue

		# Skip if the tag thinks it is at the wrong sector
		if not tag.tag_location == 256:
			continue

		# Skip if the sector is not an Anchor Volume Description Pointer
		if not tag.tag_identifier == TagIdentifier.AnchorVolumeDescriptorPointer:
			continue

		# Got the correct size
		return size

	raise Exception("Could not get file sector size.")


def read_udf_file(file_name):
	# Make sure the file exists
	if not os.path.isfile(file_name):
		raise Exception("No such file '{0}'".format(file_name))

	# Open the file
	file_size = os.path.getsize(file_name)
	file = open(file_name, 'rb')

	# Make sure the file is valid UDF
	if not is_valid_udf(file, file_size):
		raise Exception("Is not a valid UDF file '{0}'".format(file_name))

	# Make sure the file can fit all the sectors
	sector_size = get_sector_size(file, file_size)
	if file_size < 257 * sector_size:
		raise Exception("File is too small to hold all sectors '{0}'".format(file_name))

	# "5.2 UDF Volume Structure and Mount Procedure" of https://sites.google.com/site/udfintro/
	# Read the Anchor VD Pointer
	context = UdfContext(file, sector_size)
	sector = 256
	file.seek(sector * sector_size)
	buffer = file.read(512)
	tag = DescriptorTag(buffer[0 : 16])
	if not tag.tag_identifier == TagIdentifier.AnchorVolumeDescriptorPointer:
		raise Exception("The last sector was supposed to be an Archive Volume Descriptor, but was not.")
	avdp = AnchorVolumeDescriptorPointer(buffer)
	
	# Get the location of the primary volume descriptor
	pvd_sector = avdp.main_volume_descriptor_sequence_extent.extent_location
		
	# Look through all the sectors and find the partition descriptor
	logical_volume_descriptor = None
	terminating_descriptor = None
	for sector in range(pvd_sector, 257):
		# Move to the sector start
		file.seek(sector * sector_size)

		# Read the Descriptor Tag
		buffer = file.read(16)
		tag = None
		try:
			tag = DescriptorTag(buffer)
		# Skip if not valid
		except:
			continue

		# Move back to the start of the sector
		file.seek(sector * sector_size)
		buffer = file.read(512)

		if tag.tag_identifier == TagIdentifier.PrimaryVolumeDescriptor:
			desc = PrimaryVolumeDescriptor(buffer)
		elif tag.tag_identifier == TagIdentifier.AnchorVolumeDescriptorPointer:
			anchor = AnchorVolumeDescriptorPointer(buffer)
		elif tag.tag_identifier == TagIdentifier.VolumeDescriptorPointer:
			pass #VolumeDescriptorPointer(buffer)
		elif tag.tag_identifier == TagIdentifier.ImplementationUseVolumeDescriptor:
			pass #ImplementationUseVolumeDescriptor(buffer)
		elif tag.tag_identifier == TagIdentifier.PartitionDescriptor:
			partition_descriptor = PartitionDescriptor(buffer)
			start = partition_descriptor.partition_starting_location * sector_size
			length = partition_descriptor.partition_length * sector_size
			physical_partition = PhysicalPartition(file, start, length)
			context.physical_partitions[partition_descriptor.partition_number] = physical_partition
		elif tag.tag_identifier == TagIdentifier.LogicalVolumeDescriptor:
			logical_volume_descriptor = LogicalVolumeDescriptor(buffer)
		elif tag.tag_identifier == TagIdentifier.UnallocatedSpaceDescriptor:
			pass #UnallocatedSpaceDescriptor(buffer)
		elif tag.tag_identifier == TagIdentifier.TerminatingDescriptor:
			terminating_descriptor = TerminatingDescriptor(buffer)
		elif tag.tag_identifier == TagIdentifier.LogicalVolumeIntegrityDescriptor:
			pass #LogicalVolumeIntegrityDescriptor(buffer)
		elif tag.tag_identifier != 0:
			raise NotImplementedError("Unexpected Descriptor Tag :{0}".format(tag.tag_identifier))

		if logical_volume_descriptor and partition_descriptor and terminating_descriptor:
			break

	# Make sure we have all the segments we need
	if not logical_volume_descriptor:
		raise Exception("File is missing a Logical Volume Descriptor sector.")

	if not partition_descriptor:
		raise Exception("File is missing a Partition Descriptor sector.")

	if not terminating_descriptor:
		raise Exception("File is missing a Terminating Descriptor sector.")

	# Get all the logical partitions
	for i in range(len(logical_volume_descriptor.partition_maps)):
		context.logical_partitions.append(LogicalPartition.from_descriptor(context, logical_volume_descriptor, i))

	# Get the extent from the partition
	fsd_buffer = read_extent(context, logical_volume_descriptor.file_set_descriptor_location)

	tag = None
	try:
		tag = DescriptorTag(fsd_buffer)
	except:
		raise Exception("Failed to get Descriptor Tag from Partition Extent.")

	# Get the root file information from the extent
	file_set_descriptor = FileSetDescriptor(fsd_buffer)
	root_directory = File.from_descriptor(context, file_set_descriptor.root_directory_icb)
	return root_directory




