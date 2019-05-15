package minnow

import (
	"encoding/binary"
	"os"
)

// MinnowWriter represents a new file which minnow blocks can be written into.
type MinnowWriter struct {
	f *os.File

	headers, blocks int

    writers []group
    headerOffsets, headerSizes []int64
	groupBlocks []int64
    blockOffsets []int64
}

// minnowHeader is the data block written before any user data is added to the
// files.
type minnowHeader struct {
	magic, version uint64
	headers, blocks, tailStart uint64
}

// Create creates a new minnow file and returns a corresponding MinnowWriter.
func Create(fname string) *MinnowWriter {
	f, err := os.Create(fname)
	if err != nil { panic(err.Error()) }

	wr := &MinnowWriter{ f: f }

	// For now we don't need anything in the header: that will be handled in the
	// Close() method.
	err = binary.Write(wr.f, binary.LittleEndian, minnowHeader{})
	if err != nil { panic(err.Error()) }

	return wr
}

// Header writes a header block to the file and returns its header index.
func (wr *MinnowWriter) Header(x interface{}) int {
	err := binary.Write(wr.f, binary.LittleEndian, x)
	if err != nil { panic(err.Error()) }

	pos, err := wr.f.Seek(0, 1)
	if err != nil { panic(err.Error()) }
	wr.headerOffsets = append(wr.headerOffsets, pos)
	wr.headerSizes = append(wr.headerSizes, int64(binary.Size(x)))

	wr.headers++
	return wr.headers - 1
}

// Int64Group starts a new Int64 group where each block contains N int64's.
func (wr *MinnowWriter) Int64Group(N int) {
	wr.newGroup(newInt64Group(wr.blocks, N))
}

// newGroup starts a new group.
func (wr *MinnowWriter) newGroup(g group) {
	wr.writers = append(wr.writers, g)
	wr.groupBlocks = append(wr.groupBlocks, 0)

	pos, err := wr.f.Seek(0, 1)
	if err != nil { panic(err.Error()) }
	wr.blockOffsets = append(wr.blockOffsets, pos)
}

// Data writes a data block to the file within the most recent Group.
func (wr *MinnowWriter) Data(x interface{}) int {
	writer := wr.writers[len(wr.writers) - 1]
	writer.writeData(wr.f, x)

	wr.groupBlocks[len(wr.groupBlocks) - 1]++
	wr.blocks++
	return wr.blocks - 1
}

// Close writes internal bookkeeping information to the end of the file
// and closes it.
func (wr *MinnowWriter) Close() {
	// Finalize running data.
	
	defer wr.f.Close()

	tailStart, err := wr.f.Seek(0, 1)
	if err != nil { panic(err.Error()) }

	// Write default tail.

	groupSizes := make([]int64, len(wr.writers))
	groupTailSizes := make([]int64, len(wr.writers))
	groupTypes := make([]int64, len(wr.writers))
	for i := range groupSizes {
		groupSizes[i] = wr.writers[i].dataBytes()
		groupTailSizes[i] = wr.writers[i].tailBytes()
		groupTypes[i] = int64(wr.writers[i].groupType())
	}

	tailData := [][]int64{
		wr.headerOffsets, wr.headerSizes, wr.blockOffsets,
		groupSizes, groupTailSizes, groupTypes,
	}

	for _, data := range tailData{
		err = binary.Write(wr.f, binary.LittleEndian, data)
		if err != nil { panic(err.Error())}

	}

	// Write group tail.

	for _, g := range wr.writers {
		g.writeTail(wr.f)
	}

	// Write the header.

	_, err = wr.f.Seek(0, 0)
	if err != nil { panic(err.Error()) }
	
	hd := minnowHeader{
		Magic, Version,
		uint64(wr.headers), uint64(wr.blocks), uint64(tailStart),
	}
	binary.Write(wr.f, binary.LittleEndian, hd)
}
