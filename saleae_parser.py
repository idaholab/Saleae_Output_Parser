"""
A python program to parse Saleae Logic Analyzer 2 export files and make them useful.
"""

import re
import binascii
import argparse
from argparse import RawDescriptionHelpFormatter
from typing import List, Dict

__version__ = "1.1.0"

def add_arguments(argument_parser: argparse.ArgumentParser) -> None:
    """
    Builds the argument parser

    Parameters:
        argument_parser (argparse.ArgumentParser): The ArgumentParser object to build from

    Returns:
        None
    """
    argument_parser.description = "A python program to parse Saleae Logic Analyzer 2 export files."
    argument_parser.epilog = "Additional Information:\n\n\
    Reminder: Make sure to export your CSV data as Hexadecimal\n\\n\
    Analyzers (-z):\n\
        async_serial\n\
        i2c (supports --address)\n\
        can (supports --can)\n\
        spi (supports --device)\n\n\
    Devices (-s/--binary):\n\
        W25Q64FW\n\
        W25Q16JV\n\
        W25Q128JVSQ\n\
        W25Q256JV\n\
        W25Q512JV\n\
    "
    argument_parser.add_argument('-v', '--version', action='version', version='%(prog)s ' + __version__)

    argument_parser.add_argument('-z', dest='analyzer', metavar='<analyzer name>',
        help="A list of built-in analyzers. See -h for list")
    argument_parser.add_argument('-c', dest='custom_columns', metavar='<column,names>', 
        help="Comma seperated list of custom column names. Use quotes for column names with spaces. (Example: \"col1,col2,col3\")")
    argument_parser.add_argument('-d', dest='data_filter', metavar='<byte_string_hex>', 
        help="Hex values of bytes you are searching for (Example: A5)")
    argument_parser.add_argument('-b', dest='before', type=int, metavar='<number_of_rows_before>', 
        help="Number of data rows before desired hex values. Used with -d (does not work --address)")
    argument_parser.add_argument('-a', dest='after', type=int, metavar='<number_of_rows_after>', 
        help="Number of data rows after desired hex values. Used with -d (does not work --address)")
    argument_parser.add_argument('-o', dest='output_file', metavar='<name_of_output_file.txt>', 
        help="Name of output filed (default: output.txt)")
    argument_parser.add_argument('-f', dest='column_filter', metavar='<name_of_column>',
        help="Output a single column (does not work with other filters)")
    argument_parser.add_argument('--device', dest='device', metavar='<name_of_device>', 
        help="A list of supported devices for SPI read. Use with -s. See -h for list")
    argument_parser.add_argument('--address', dest='address', metavar='<hex_address>', 
        help="Filter on certain address value if analyzer supports it. Might have unexpected results if used with -d. See -h for list")
    argument_parser.add_argument('--can', dest='can_out', action='store_true', 
        help="Special formated output for the CAN analyzer (does not work with other filters)")
    argument_parser.add_argument('-s', dest='srecord', action='store_true', 
        help="Convert output stream into srecord for compatible devices (does not work with other filters)")
    argument_parser.add_argument('--binary', dest='binary', action='store_true', 
        help="Convert output stream into raw binary file for compatible devices (does not work with other filters)")
    argument_parser.add_argument(dest='in_file', metavar='FILE', help="Saleae export data file")

class Analyzer():
    """
    This is the base class for the Analyzers

    Attributes:
        columns (List):         A list of the default Saleae Logic 2 column names
        file (str):             The path to the Saleae output text/csv file
        data_filter (str):      A hex value to filter for if -d is used
        header_pos (Dict):      A dictionary that contains the index positions of column headers
        headers (List):         A list of header names parsed from output text file
        results (List):         A list that contains the results from 'read_file'
        col_filter (str):       The column value to filter on in 'print_results' if -f is used
        before (int):           The number of lines to print before the data_filter matched value
        after (int):            The number of lines to print after the data_filter matched value
        address (str):          The address to filter on for the I2C analyzer
        can (bool):             A flag to enable the special 'print_results' output for the CAN analyzer
    """

    def __init__(self, args):
        """
        The constructor for Analyzer class

        Parameters:
            args (argparse.Namespace): Object returned from 'parse_args'

        """
        self.columns = ['Time [s]', 'name', 'type', 'start_time', 'duration']
        self.file = args.in_file
        self.data_filter = args.data_filter
        self.header_pos = {}
        self.headers = []
        self.results = []
        
        if args.custom_columns:
            self.parse_custom_columns(args.custom_columns)

        if args.column_filter:
            self.col_filter = args.column_filter

        if args.before:
            self.before = args.before
        
        if args.after:
            self.after = args.after

        if args.address:
            self.address = args.address

        if args.can_out:
            self.can = args.can_out

    def parse_custom_columns(self, cols: str) -> None:
        """
        Parses input argument string and puts it into a list

        Parameters:
            cols (str): A comma seperated string that contains values for custom columns

        Returns:
            None
        """
        entries = cols.split(',')
        for entry in entries:
            self.columns.append(entry)

    def sort_rows(self, entry: Dict) -> str:
        """
        Sorts a list based on value of 'Time [s]' or 'start_time' columns

        Parameters:
            entry (str): A dictionary entry from the list being sorted

        Returns:
            str: The value to be sorted
        """
        if 'Time [s]' in self.header_pos:
            return entry['val'][self.header_pos['Time [s]']]
        elif 'start_time' in self.header_pos:
            return entry['val'][self.header_pos['start_time']]

    def divide_chunks(self, l: List, n: int) -> List:
        """
        Divides a list into n-sized lists

        Parameters:
            l (List): The large list to be divided
            n (int): The size of the split lists (chunks)

        Returns:
            List: Returns a list of n-size (or the remaining)
        """
        for i in range(0, len(l), n):
            yield l[i:i+n]

    def read_file(self):
        """
        The base Analyzer funtion for reading and parsing the Saleae Logic 2 output text files

        Parameters:

        Returns:
            None
        """        
        first_line = False
        header_pos_count = 0
        before_buffer = []
        after_buffer = []

        with open(self.file, 'r') as infile:
            for line in infile:
                line = line.rstrip()
                if not first_line:
                    self.headers = line.split(',')
                    first_line = True
                    
                    for h in self.headers:
                        self.header_pos[h.strip('"')] = header_pos_count
                        header_pos_count += 1
                else:
                    values = line.split(',')
                    if self.data_filter:
                        if re.search(self.data_filter, line, re.IGNORECASE):
                            if len(self.results) > 0:
                                self.results[-1]['after'] = after_buffer
                            self.results.append({'val': values, 'before': before_buffer})
                            before_buffer = []
                            after_buffer = []
                        else:
                            if hasattr(self, "before"):
                                if len(before_buffer) < self.before:
                                    before_buffer.append(values)
                                else:
                                    before_buffer.pop(0)
                                    before_buffer.append(values)
                            if hasattr(self, "after") and len(self.results) > 0:
                                if len(after_buffer) < self.after:
                                    after_buffer.append(values)
                                else:
                                    if 'after' not in self.results[-1]:
                                        self.results[-1]['after'] = after_buffer
                    else:
                        self.results.append({'val': values})

        # Make sure '\n' character doesn't ruin row size
        for idx, r in enumerate(self.results):
            if len(r['val']) < len(self.headers):       
                while(len(r['val']) < len(self.headers)):
                    self.results[idx]['val'][-1] = self.results[idx]['val'][-1] + '\x0a' + self.results[idx+1]['val'][0]
                    self.results[idx]['val'] = self.results[idx]['val'] + self.results[idx+1]['val'][1:]
                    self.results.pop(idx+1)

        # The file should already by sorted, so this is likely not needed
        #self.results.sort(key=self.sort_rows)

    def print_results(self):
        """
        The base Analyzer funtion for printing the results of the parsed Saleae output text file

        Parameters:

        Returns:
            None
        """        
        if hasattr(self, "col_filter"):
            print(f"Column Filter: {self.col_filter}")
            print()
        else:
            print(self.headers)
            print()

        for r in self.results:
            if hasattr(self, "col_filter"):
                if self.col_filter in self.header_pos:
                    if r['val'][self.header_pos[self.col_filter]] != '':
                        print(r['val'][self.header_pos[self.col_filter]])
                else:
                    print("Column filter value doesn't exists in file")
                    print("Avaiable Columns:")
                    for h in self.headers:
                        print(h)
                    break
            else:
                if hasattr(self, "before") and self.data_filter:
                        for b in r['before']:
                            print(f"{b}")
                print(r['val'])
                if hasattr(self, "after") and self.data_filter:
                        for a in r['after']:
                            print(f"{a}")
                if hasattr(self, "before") or hasattr(self, "after"):
                    if self.data_filter:
                        print()


class SPI(Analyzer):
    """
    SPI class that expands functionality of Analyzer class

    Attributes:
        extra_cols (List):      Saleae Logic 2 default columns that are specific to the SPI analyzer
        devices (Dict):         Tested and verified IC devices that can have their reads converted to an srecord  
    """

    def __init__(self, args):
        """
        The constructor for SPI class

        Parameters:
            args (argparse.Namespace): Object returned from 'parse_args'

        """
        super().__init__(args)
        self.extra_cols = ['"mosi"', '"miso"', 'Packet ID', 'MOSI', 'MISO'] 
        self.devices = {
            "DEFAULT": {'READ': '03', 'FAST_READ': '0B', 'FAST_DUAL_READ': '3B', 'FAST_QUAD_READ': 'EB', 'SIZE': 0x3FFFFFF+256},
            "W25Q64FW": {'READ': '03', 'FAST_READ': '0B', 'FAST_DUAL_READ': '3B', 'FAST_QUAD_READ': 'EB', 'SIZE': 0x7FFFFF+256},
            "W25Q16JV": {'READ': '03', 'FAST_READ': '0B', 'FAST_DUAL_READ': '3B', 'FAST_QUAD_READ': 'EB', 'SIZE': 0x1FFFFF+256},
            "W25Q128JVSQ": {'READ': '03', 'FAST_READ': '0B', 'FAST_DUAL_READ': '3B', 'FAST_QUAD_READ': 'EB', 'SIZE': 0xFFFFFF+256},
            "W25Q256JV": {'READ': '03', 'FAST_READ': '0B', 'FAST_DUAL_READ': '3B', 'FAST_QUAD_READ': 'EB', 'SIZE': 0x1FFFFFF+256},
            "W25Q512JV": {'READ': '03', 'FAST_READ': '0B', 'FAST_DUAL_READ': '3B', 'FAST_QUAD_READ': 'EB', 'SIZE': 0x3FFFFFF+256}
            }

        if args.device:
            if args.device in self.devices:
                self.device = self.devices[args.device]
            else:
                print("Unknown device given. Using DEFAULT")
                self.device = self.devices['DEFAULT']
        else:
            self.device = self.devices['DEFAULT']

        for c in self.extra_cols:
            self.columns.append(c)

    def read_file(self):
        """
        The SPI function override of 'read_file' that handles reading MOSI and MISO to output as an srecord

        Parameters:

        Returns:
            None
        """        
        if args.srecord or args.binary:
            
            first_line = False
            header_pos_count = 0
            mosi_val = ''
            miso_val = ''
            data_buf = []
            command_found = False
            count = 0
            address = ''
            res_count = 0

            print("Reading export file...")

            with open(self.file, 'r') as infile:
                for i, line in enumerate(infile):
                    line = line.rstrip()
                    if not first_line:
                        self.headers = line.replace('"','').split(',')
                        first_line = True
                        
                        for h in self.headers:
                            self.header_pos[h] = header_pos_count
                            header_pos_count += 1
                    else:
                        # Check weird case if last quote is put on newline by itself
                        values = line.split(',')
                        if len(values) != len(self.header_pos):
                            line += '"'
                        values = line.split(',')
                        if len(values) != len(self.header_pos):
                            print(f"WARNING: Trouble finding all columns for line {i}")
                            continue
                        
                        # Parser when using Export Table which contains "type" header
                        if 'type' in self.headers:
                            if values[self.header_pos['type']] == '"disable"':
                                if command_found:
                                    command_found = False
                                    self.results.append({'address': address, 'data': data_buf})
                                    address = ''
                                    data_buf = []
                                    count = 0
                                    res_count = 0
                                    #print(f"Line number: {i}")
                                    #print(self.results[-1])
                                else:
                                    res_count = 0
                                       
                            elif values[self.header_pos['type']] == '"result"':
                                if 'miso' in self.headers:
                                    mosi_val = values[self.header_pos['mosi']].replace('0x','')
                                    miso_val = values[self.header_pos['miso']].replace('0x','')
                                else:
                                    print("ERROR: Can't find SPI header 'miso' or 'MISO'")
                                    return
                                
                                if not command_found:
                                    if mosi_val == self.device['READ'] and res_count == 0:
                                        command_found = self.device['READ']
                                        count +=1
                                    elif mosi_val == self.device['FAST_READ'] and res_count == 0:
                                        command_found = self.device['FAST_READ']
                                    elif mosi_val == self.device['FAST_DUAL_READ'] and res_count == 0:
                                        command_found = self.device['FAST_DUAL_READ']
                                    elif mosi_val == self.device['FAST_QUAD_READ'] and res_count == 0:
                                        command_found = self.device['FAST_QUAD_READ']
                                    else:
                                        res_count += 1
                                    continue
                                else:
                                    # If READ, first 3 bytes address, then read MISO until "type" = "disable"
                                    # TODO: Addresses can sometimes be 4 bytes with 0x13 command (Read Data with 4 byte address)
                                    if command_found == self.device['READ']:
                                        if count <= 3:
                                            address += mosi_val
                                        elif count > 3:
                                            data_buf.append(miso_val)
                                        count += 1
                                    # If FAST_READ, first 3 bytes address, skip next byte (8 dummy clocks), then read MISO until "type" = "disable"
                                    elif command_found == self.device['FAST_READ']:
                                        if count <= 3:
                                            address += mosi_val
                                        elif count == 4:
                                            pass
                                        elif count > 4:
                                            data_buf.append(miso_val)
                                        count += 1
                                    # If FAST_DUAL_READ, first 3 bytes address, skip next byte, then read both MISO and MOSI
                                    elif command_found == self.device['FAST_DUAL_READ']:
                                        if count <= 3:
                                            address += mosi_val
                                        elif count == 4:
                                            pass
                                        elif count > 4:
                                            # MISO has odd bits (7,5,3,1|7,5,3,1)
                                            # MOSI has even bits (6,4,2,0|6,4,2,0)
                                            a = int(miso_val,16)
                                            b = int(mosi_val,16)
                                            nibble_up_a = (a & 0xf0) >> 4
                                            nibble_low_a = (a & 0x0f)
                                            nibble_up_b = (b & 0xf0) >> 4
                                            nibble_low_b = (b & 0x0f)
                                            upper_byte = (((nibble_up_a&0x8)<<4) | ((nibble_up_b&0x8)<<3) | ((nibble_up_a&0x4)<<3) |
                                                    ((nibble_up_b&0x4)<<2) | ((nibble_up_a&0x2)<<2) | ((nibble_up_b&0x2)<<1) |
                                                    ((nibble_up_a&0x1)<<1) | (nibble_up_b&0x1))
                                            lower_byte = (((nibble_low_a&0x8)<<4) | ((nibble_low_b&0x8)<<3) | ((nibble_low_a&0x4)<<3) |
                                                    ((nibble_low_b&0x4)<<2) | ((nibble_low_a&0x2)<<2) | ((nibble_low_b&0x2)<<1) |
                                                    ((nibble_low_a&0x1)<<1) | (nibble_low_b&0x1))
                                            data_buf.append('0x{0:0{1}X}'.format(upper_byte,2).replace('0x','').upper())
                                            data_buf.append('0x{0:0{1}X}'.format(lower_byte,2).replace('0x','').upper())
                                        count += 1
                                    elif command_found == self.device['FAST_QUAD_READ']:
                                        #Need to handle custom defined columns for the other two data pins
                                        #TODO
                                        count +=1
                        # Parser for SPI Analyzer export which has no "type"
                        # TODO: This needs fixing
                        else:
                            if 'miso' in self.headers:
                                mosi_val = values[self.header_pos['mosi']].replace('0x','')
                                miso_val = values[self.header_pos['miso']].replace('0x','')
                            elif 'MISO' in self.headers:
                                mosi_val = values[self.header_pos['MOSI']].replace('0x','')
                                miso_val = values[self.header_pos['MISO']].replace('0x','')
                            else:
                                print("ERROR: Can't find SPI header 'miso' or 'MISO'")
                                return
                            # Check to see if we are at a new command
                            if command_found and count > 4:
                                if mosi_val == self.device['READ'] or mosi_val == self.device['FAST_READ'] or mosi_val == self.device['FAST_DUAL_READ'] or mosi_val == self.device['FAST_QUAD_READ']:
                                    command_found = False
                                    self.results.append({'address': address, 'data': data_buf})
                                    address = ''
                                    data_buf = []
                                    count = 0
                            if not command_found:
                                if mosi_val == self.device['READ']:
                                    command_found = self.device['READ']
                                    count +=1
                                elif mosi_val == self.device['FAST_READ']:
                                    command_found = self.device['FAST_READ']
                                    count +=1
                                elif mosi_val == self.device['FAST_DUAL_READ']:
                                    command_found = self.device['FAST_DUAL_READ']
                                    count +=1
                                elif mosi_val == self.device['FAST_QUAD_READ']:
                                    command_found = self.device['FAST_QUAD_READ']
                                    count +=1
                                continue
                            else:
                                # If READ, read MISO until MOSI is not 0xFF
                                if command_found == self.device['READ']:
                                    if count <= 3:
                                        address += mosi_val
                                    #elif count > 3 and mosi_val == 'FF':
                                    elif count > 3:
                                        data_buf.append(miso_val)
                                    count += 1
                                # If FAST_READ, skip next byte (8 dummy clocks), then read MISO until MOSI is not 0xFF
                                elif command_found == self.device['FAST_READ']:
                                    if count <= 3:
                                        address += mosi_val
                                    elif count == 4:
                                        pass
                                    #elif count > 4 and mosi_val == 'FF':
                                    elif count > 4:
                                        data_buf.append(miso_val)
                                    count += 1
                                # If FAST_DUAL_READ, skip next byte, then read both MISO and MOSI until another command is seen
                                elif command_found == self.device['FAST_DUAL_READ']:
                                    if count <= 3:
                                        address += mosi_val
                                    elif count == 4:
                                        pass
                                    elif count > 4:
                                        # MISO has odd bits (7,5,3,1|7,5,3,1)
                                        # MOSI has even bits (6,4,2,0|6,4,2,0)
                                        #print(line)
                                        a = int(miso_val,16)
                                        b = int(mosi_val,16)
                                        nibble_up_a = (a & 0xf0) >> 4
                                        nibble_low_a = (a & 0x0f)
                                        nibble_up_b = (b & 0xf0) >> 4
                                        nibble_low_b = (b & 0x0f)
                                        upper_byte = (((nibble_up_a&0x8)<<4) | ((nibble_up_b&0x8)<<3) | ((nibble_up_a&0x4)<<3) |
                                                ((nibble_up_b&0x4)<<2) | ((nibble_up_a&0x2)<<2) | ((nibble_up_b&0x2)<<1) |
                                                ((nibble_up_a&0x1)<<1) | (nibble_up_b&0x1))
                                        lower_byte = (((nibble_low_a&0x8)<<4) | ((nibble_low_b&0x8)<<3) | ((nibble_low_a&0x4)<<3) |
                                                ((nibble_low_b&0x4)<<2) | ((nibble_low_a&0x2)<<2) | ((nibble_low_b&0x2)<<1) |
                                                ((nibble_low_a&0x1)<<1) | (nibble_low_b&0x1))
                                        data_buf.append('0x{0:0{1}X}'.format(upper_byte,2).replace('0x','').upper())
                                        data_buf.append('0x{0:0{1}X}'.format(lower_byte,2).replace('0x','').upper())
                                    count += 1
                                elif command_found == self.device['FAST_QUAD_READ']:
                                    #Need to handle custom defined columns for the other two data pins
                                    #TODO
                                    count +=1
                #self.results.append({'address': address, 'data': data_buf})
        else:
            return super().read_file()

    def print_results(self):
        """
        The SPI function override of 'print_results' that handles converting the results to an srecord if -s is chosen

        Parameters:

        Returns:
            None
        """        
        if args.srecord:
            for entry in self.results:
                SRECORD_DATA_SIZE = 32
                address_size = 3
                checksum_size = 1
                data_len = len(entry['data'])

                if data_len > SRECORD_DATA_SIZE:
                    data_chunks = list(self.divide_chunks(entry['data'], SRECORD_DATA_SIZE))
                else:
                    data_chunks = entry['data']

                for chunk in data_chunks:
                    byte_count = len(chunk) + address_size + checksum_size
                    if byte_count <= 15:
                        byte_count = '0' + hex(byte_count).split('0x')[1]
                    else:
                        byte_count = hex(byte_count).split('0x')[1]

                    # Sum bytes
                    temp_checksum = 0
                    for b in [entry['address'][i:i+2] for i in range(0, len(entry['address']), 2)]:
                        temp_checksum = temp_checksum + int(b,16)
                    for b in chunk:
                        temp_checksum = temp_checksum + int(b,16)
                    checksum = int(byte_count, 16) + temp_checksum
                    checksum = hex(checksum).split('0x')[1]
                    # Get LSB
                    checksum = checksum[-2:]
                    # Take one's compliment
                    checksum = hex(int(checksum,16) ^ int('ff',16)).split('0x')[1]
                    # Uppercase
                    checksum = checksum.upper()
                    # Prepend 0
                    if len(checksum) == 1:
                        checksum = '0' + checksum
                    print("S2%s%s%s%s" % (byte_count, entry['address'], ''.join(chunk), checksum))

                    #Update address for when there are multiple chunks
                    entry['address'] = "{:0>6x}".format(int(entry['address'], 16) + SRECORD_DATA_SIZE).upper()
        elif args.binary:
            mem_map = [b'\x00']*self.device['SIZE']
            #seq_reads = b''

            print("Writing binary files...")
            result_entry_len = len(self.results)
            print("Writing seq_read.bin")
            with open('seq_read.bin','wb') as fd:
                for idx, entry in enumerate(self.results):
                    #print(f"{idx}/{result_entry_len} rows", end='\r')
                    #print(f"ADDRESS: {entry['address']}")
                    for i, entry_byte in enumerate(entry['data']):
                        addr_offset = int(entry['address'],16) + i
                        #print(f"Byte: {entry_byte} at offset {addr_offset} ({hex(addr_offset)}))")
                        #print(f"addr: {entry['address']}, index: {i}, offset: {addr_offset}")
                        mem_map[addr_offset] = bytes.fromhex(entry_byte)
                        #print(f"Value: {mem_map[addr_offset]}")
                        #seq_reads += bytes.fromhex(entry_byte)
                        fd.write(bytes.fromhex(entry_byte))

            print("Writing mem_map.bin")
            with open('mem_map.bin','wb') as fd:
                for b in mem_map:
                    fd.write(b)

        else:
            return super().print_results()

class AsyncSerial(Analyzer):
    """
    AsyncSerial class that expands functionality of Analyzer class

    Attributes:
        extra_cols (List):      Saleae Logic 2 default columns that are specific to the SPI analyzer
    """

    def __init__(self, args):
        """
        The constructor for AsyncSerial class

        Parameters:
            args (argparse.Namespace): Object returned from 'parse_args'
        """
        super().__init__(args)
        self.extra_cols = ['"data"', '"error"', 'Value', 'Parity Error', 'Framing Error']
        
        for c in self.extra_cols:
            self.columns.append(c)

class CAN(Analyzer):
    """
    CAN class that expands functionality of Analyzer class

    Attributes:
        extra_cols (List):      Saleae Logic 2 default columns that are specific to the SPI analyzer
    """

    def __init__(self, args):
        """
        The constructor for CAN class

        Parameters:
            args (argparse.Namespace): Object returned from 'parse_args'
        """
        super().__init__(args)
        self.extra_cols = ['"data"','"identifier"','"num_data_bytes"','"crc"','"ack"']
        
        for c in self.extra_cols:
            self.columns.append(c)

    def read_file(self):
        """
        The CAN function override of 'read_file' that handles reading CAN identifiers

        Parameters:

        Returns:
            None
        """        
        if hasattr(self, "can"):
            first_line = False
            header_pos_count = 0
            identifier = False
            self.id_counter = {}

            with open(self.file, 'r') as infile:
                for line in infile:
                    line = line.rstrip()
                    if not first_line:
                        self.headers = line.split(',')
                        first_line = True
                        
                        for h in self.headers:
                            self.header_pos[h.strip('"')] = header_pos_count
                            header_pos_count += 1
                    else:
                        values = line.split(',')
                        if values[self.header_pos['type']] == '"identifier_field"':
                            if not identifier:
                                temp_entry = {'id': values[self.header_pos['identifier']], 'data': []}
                                identifier = True
                                self.id_counter[values[self.header_pos['identifier']]] = 1
                            else:
                                self.results.append(temp_entry)
                                temp_entry = {'id': values[self.header_pos['identifier']], 'data': []}
                                if values[self.header_pos['identifier']] in self.id_counter:
                                    self.id_counter[values[self.header_pos['identifier']]] += 1
                                else:
                                    self.id_counter[values[self.header_pos['identifier']]] = 1
                        elif values[self.header_pos['type']] == '"data_field"':
                            if identifier:
                                temp_entry['data'].append(values[self.header_pos['data']])

            # The file should already by sorted, so this is likely not needed
            #self.results.sort(key=self.sort_rows)
        else:
            return super().read_file()

    def print_results(self):
        """
        The CAN function override of 'print_results' that handles printing CAN identifiers along with its data

        Parameters:

        Returns:
            None
        """        
        spacer = "|"
        if hasattr(self, "can"):
            print("CAN Special Output")
            for id in self.id_counter:
                print(f"ID: {id}\tCount:{self.id_counter[id]}")
            print()

            for r in self.results:
                print(r['id'])
                for d in r['data']:
                    if '0x' in d:
                        ascii_val = d[2:]
                    else:
                        ascii_val = d
                    ascii_val = binascii.unhexlify(ascii_val)
                    ascii_val = ascii_val.decode(errors='replace')
                    print(f"{d}{spacer:>4}{ascii_val:>4}")
                print()
        else:
            return super().print_results()

class I2C(Analyzer):
    """
    I2C class that expands functionality of Analyzer class

    Attributes:
        extra_cols (List):      Saleae Logic 2 default columns that are specific to the SPI analyzer
    """

    def __init__(self, args):
        """
        The constructor for I2C class

        Parameters:
            args (argparse.Namespace): Object returned from 'parse_args'
        """
        super().__init__(args)
        self.extra_cols = ['"ack"', '"address"', '"read"', '"data"', '"Packet ID"', 
        '"Address"', '"Data"', '"Read/Write"', '"ACK/NAK"']

        for c in self.extra_cols:
            self.columns.append(c)

    def print_results(self):
        """
        The I2C function override of 'print_results' that handles printing by a specific I2C address

        Parameters:

        Returns:
            None
        """        
        if hasattr(self, "address"):
            print(f"Address: {self.address}")

            for idx, r in enumerate(self.results):
                if hasattr(self, "address"):
                    if "address" in self.header_pos:
                        addr_col_name = "address"
                        if self.address in r['val'][self.header_pos[addr_col_name]]:
                            print(r['val'])
                            while (idx+1) < len(self.results) and self.results[idx+1]['val'][self.header_pos["type"]] == '"data"':
                                idx += 1
                                print(self.results[idx]['val'])
                            print()
                    elif "Address" in self.header_pos:
                        addr_col_name = "Address"
                        if self.address in r['val'][self.header_pos[addr_col_name]]:
                            print(r['val'])
        else:
            return super().print_results()

if __name__ == "__main__":

    parser = argparse.ArgumentParser(formatter_class=RawDescriptionHelpFormatter)
    add_arguments(parser)
    args = parser.parse_args()

    if args.analyzer == 'async_serial':
        analyzer = AsyncSerial(args)
    elif args.analyzer == 'spi':
        analyzer = SPI(args)
    elif args.analyzer == 'i2c':
        analyzer = I2C(args)
    elif args.analyzer == 'can':
        analyzer = CAN(args)
    else:
        analyzer = Analyzer(args)

    analyzer.read_file()
    analyzer.print_results()