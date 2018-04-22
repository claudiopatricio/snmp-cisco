#!/usr/bin/env python

# Copyright (c) 2018 Cláudio Patrício
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import sys
import platform
import os
import os.path
import datetime
import json
import re
import argparse
import subprocess
from time import *
from snimpy.manager import *
from tabulate import tabulate

def getTerminalSize():
	import os
	env = os.environ
	def ioctl_GWINSZ(fd):
		try:
			import fcntl, termios, struct, os
			cr = struct.unpack('hh', fcntl.ioctl(fd, termios.TIOCGWINSZ,'1234'))
		except:
			return
		return cr
	cr = ioctl_GWINSZ(0) or ioctl_GWINSZ(1) or ioctl_GWINSZ(2)
	if not cr:
		try:
			fd = os.open(os.ctermid(), os.O_RDONLY)
			cr = ioctl_GWINSZ(fd)
			os.close(fd)
		except:
			pass
	if not cr:
		cr = (env.get('LINES', 25), env.get('COLUMNS', 80))
	return int(cr[1]), int(cr[0])

def IPfromOctetString(t,s):
	if t==1 or t==3:	#IPv4 global, non-global
		return '.'.join(['%d' % ord(x) for x in s])
	elif t==2 or t==4:	#IPv6 global, non-global
		a=':'.join(['%02X%02X' % (ord(s[i]),ord(s[i+1])) for i in range(0,16,2)])
		return re.sub(':{1,}:','::',re.sub(':0*',':',a))

def getStructure(m):
	aux = {}
	for addr, i in m.ipAddressIfIndex.iteritems():
		if i not in aux.iteritems():
			aux.update({i: {
				'name': m.ifDescr[i],
				'address': IPfromOctetString(addr[0],addr[1]),
				'time': time(),
				'timedate': datetime.datetime.fromtimestamp(time()).strftime('%H:%M:%S %d/%m/%Y'),
				'if-mib': {
					'ifHCOutUcastPkts': 0,
					'ifHCInUcastPkts': 0,
					'ifHCOutOctets': 0,
					'ifHCInOctets': 0,
					'ifSpeed': 0,
				},
				'cisco-queue-mib': {
					'cQStatsDepth': 0,
				},
			}})
	return aux

def writeLog(data, logfile):
	aux = open(logfile, "w+b")
	data = json.dumps(data)
	aux.write(data)
	aux.close()

def readLog(logfile):
	try:
		aux = open(logfile, "r").read()
		return json.loads(aux)
	except:
		return None

def printStats(data, interface):
	if len(data) < 1:
		print "ERROR: No data to show!!!"
	if str(interface) not in data[0].keys():
		interface = int(data[0].keys()[0])
	toprint = []
	toprint_headers = []
	index = len(data) - 2
	for i in data[index]:
		toprint_aux = []
		toprint_aux.append(data[index][i]['name'].replace("FastEthernet", "FE").replace("Loopback", "LO"))
		toprint_headers.append("Name")
		toprint_aux.append(data[index][i]['address'])
		toprint_headers.append("IP")
		for k, val in data[index][i]['if-mib'].iteritems():
			toprint_headers.append(k)
			if k == 'ifSpeed':
				toprint_aux.append(str(val/1000000) + "Mbps")
			elif 'Pkts' in k:
				toprint_aux.append(str(val) + " packets (" + str(round((((val - data[0][i]['if-mib'][k]) / (data[index][i]['time']-data[0][i]['time']))),2)) + " p/s)")
			else:
				toprint_aux.append(str(val) + " bytes (" + str(round((((val - data[0][i]['if-mib'][k]) * 8 / ((data[index][i]['time']-data[0][i]['time']) * 1024))),2)) + " Kbps)")
		for k, val in data[index][i]['cisco-queue-mib'].iteritems():
			toprint_headers.append(k)
			toprint_aux.append(str(val))
		toprint.append(toprint_aux)
	print tabulate(toprint, headers=toprint_headers, tablefmt='fancy_grid', numalign='center')
	try:
		gnuplot = subprocess.Popen(["/usr/bin/gnuplot"], stdin=subprocess.PIPE)
		aux = []
		aux_calc = 0
		aux_octets = 0
		aux_max_calc = 0
		aux_time = 0
		aux_time_base = 0
		for x in data[-20:]:
			if aux_octets == 0:
				aux_calc = 0
				aux_octets = x[str(interface)]["if-mib"]["ifHCOutOctets"] + x[str(interface)]["if-mib"]["ifHCInOctets"]
				aux_time = x[str(interface)]["time"]
				aux_time_base = x[str(interface)]["time"]
				aux.append((0,0))
				gnuplot.stdin.write("set xlabel 'Since %s (in seconds)'\n" % x[str(interface)]["timedate"])
			else:
				aux_calc = (x[str(interface)]["if-mib"]["ifHCOutOctets"] + x[str(interface)]["if-mib"]["ifHCInOctets"] - aux_octets) * 8 / ((x[str(interface)]["time"] - aux_time) * 1024)# * x[1]["if-mib"]["ifSpeed"])
				aux_octets = x[str(interface)]["if-mib"]["ifHCOutOctets"] + x[str(interface)]["if-mib"]["ifHCInOctets"]
				if aux_calc > aux_max_calc:
					aux_max_calc = aux_calc
				aux.append((float(x[str(interface)]["time"] - aux_time_base), float(aux_calc)))
				aux_time = x[str(interface)]["time"]
		x,y = getTerminalSize()
		gnuplot.stdin.write("set term dumb %d %d\n" % (x, y-20))
		if aux_max_calc > 0:
			gnuplot.stdin.write("set yrange [0:%f]\n" % float(aux_max_calc))
		else:
			gnuplot.stdin.write("set yrange [0:1]\n")
		#gnuplot.stdin.write("set xlabel 'kbps'\n")
		#gnuplot.stdin.write("set ylabel 'kbps'\n")
		gnuplot.stdin.write("set title '%s'\n" % data[0][str(interface)]["name"])
		gnuplot.stdin.write("plot '-' using 1:2 title 'kbps' with linespoints \n")
		for i,j in aux:
			gnuplot.stdin.write("%f %f\n" % (i,j))
		gnuplot.stdin.write("e\n")
		gnuplot.stdin.flush()
	except:
		gnuplot.terminate()
	return

def main():
	mib.path(mib.path()+":/usr/share/mibs/cisco")
	load("SNMPv2-MIB") # For sysDescr
	load("IF-MIB")
	load("IP-MIB")
	#load("RFC1213-MIB")
	load("CISCO-QUEUE-MIB")
	
	parser = argparse.ArgumentParser()
	parser.add_argument('-r', '--router', nargs='?', help='address of router to monitor')
	parser.add_argument('-s', '--sinterval', type=int, help='sampling interval (seconds)',default=5)
	parser.add_argument('-i', '--interface', type=int, help='network interface id', default=1)
	parser.add_argument('-l', '--log', type=str, help='log filename')
	args=parser.parse_args()
	
	if not args.log and not args.router:
		parser.print_help()
		return 0
	
	if args.log and os.path.isfile(args.log):
		if sys.stdout.isatty() and platform.system().lower() != 'windows':
			os.system("clear")
		else:
			os.system("cls")
		print "Statistics from log %s" % args.log
		printStats(readLog(args.log), args.interface)
		return

	m = Manager(args.router, 'private', 3, secname='uDDR', authprotocol="MD5", authpassword="authpass", privprotocol="AES", privpassword="privpass")

	interfaces = [] # name, address, if-mib, cisco-queue-mib
	index = 0
	time_start = 0
	time_interval = args.sinterval # 5 seconds
	if args.interface not in m.ifDescr.keys():
		print "Wrong interface, using %s (id: %d)" % (m.ifDescr.items()[0][1], m.ifDescr.items()[0][0])
		interface = m.ifDescr.items()[0][0]
	else:
		interface = args.interface

	try:
		gnuplot = subprocess.Popen(["/usr/bin/gnuplot"], stdin=subprocess.PIPE)
		while(True):
			time_start = time()
			interfaces.append(getStructure(m))
			for i in interfaces[index][interfaces[index].keys()[0]]['if-mib'].keys():
				for k, value in m.__getattribute__(i).iteritems():
					if k in interfaces[index].keys():
						interfaces[index][k]['if-mib'][i] = value # k-> interface, i-> type

			for i in interfaces[index][interfaces[index].keys()[0]]['cisco-queue-mib'].keys():
				for k, value in m.__getattribute__(i).iteritems():
					if k[0] in interfaces[index].keys() and k[1] == 2: # FIFO (Always 2)
						interfaces[index][k[0]]['cisco-queue-mib'][i] = value
					else:
						interfaces[index][k[0]]['cisco-queue-mib'][i] = -1

			if sys.stdout.isatty() and platform.system().lower() != 'windows':
				os.system("clear")
			else:
				os.system("cls")
			print(m.sysDescr) ## Router Description (Global Information)
			print ""
			toprint = []
			toprint_headers = []#["Name", "IP", "ifSpeed", "ifHCOutUcastPkts", "ifHCInUcastPkts", "ifHCOutOctets", "ifHCInOctets"]
			for i in interfaces[index]:
				toprint_aux = []
				toprint_aux.append(interfaces[index][i]['name'].replace("FastEthernet", "FE").replace("Loopback", "LO"))
				toprint_headers.append("Name")
				toprint_aux.append(interfaces[index][i]['address'])
				toprint_headers.append("IP")
				#print "==========================================================="
				#print "Interface " + interfaces[index][i]['name'] + " (" + interfaces[index][i]['address'] + ")" + ":"
				for k, val in interfaces[index][i]['if-mib'].iteritems():
					toprint_headers.append(k)
					if k == 'ifSpeed':
						#print "\t" + k + ": " + str(val/1000000) + "Mbps"
						toprint_aux.append(str(val/1000000) + "Mbps")
					elif 'Pkts' in k:
						if index > 0:
							#print "\t" + k + ": " + str(val) + " packets (" + str(round((((val - interfaces[index-1][i]['if-mib'][k]) / (time()-time_start))),2)) + " packets/s)"
							toprint_aux.append(str(val) + " packets (" + str(round((((val - interfaces[index-1][i]['if-mib'][k]) / (interfaces[index][i]['time']-interfaces[index-1][i]['time']))),2)) + " p/s)")
						else:
							#print "\t" + k + ": " + str(val) + " packets"
							toprint_aux.append(str(val) + " packets")
					else:
						if index > 0:
							#print "\t" + k + ": " + str(val) + " bytes (" + str(round((((val - interfaces[index-1][i]['if-mib'][k]) * 800 / ((time()-time_start) * interfaces[index][i]['if-mib']['ifSpeed']))),2)) + " Kbps)"
							toprint_aux.append(str(val) + " bytes (" + str(round((((val - interfaces[index-1][i]['if-mib'][k]) * 8 / ((interfaces[index][i]['time']-interfaces[index-1][i]['time']) * 1024))),2)) + " Kbps)")
						else:
							#print "\t" + k + ": " + str(val) + " bytes"
							toprint_aux.append(str(val) + " bytes")
				for k, val in interfaces[index][i]['cisco-queue-mib'].iteritems():
					#print "\t" + k + ": " + str(val)
					toprint_headers.append(k)
					toprint_aux.append(str(val))
				toprint.append(toprint_aux)
			print tabulate(toprint, headers=toprint_headers, tablefmt='fancy_grid', numalign='center')
			aux = []
			aux_calc = 0
			aux_octets = 0
			aux_max_calc = 0
			aux_time = 0
			for x in interfaces[-20:]:
					if aux_octets == 0:
						aux_calc = 0
						aux_octets = x[interface]["if-mib"]["ifHCOutOctets"] + x[interface]["if-mib"]["ifHCInOctets"]
						aux_time = x[interface]["time"]
						aux.append((0,0))
						gnuplot.stdin.write("set xlabel 'Since %s (in seconds)'\n" % x[interface]["timedate"])
					else:
						aux_calc = (x[interface]["if-mib"]["ifHCOutOctets"] + x[interface]["if-mib"]["ifHCInOctets"] - aux_octets) * 8 / ((x[interface]["time"] - aux_time) * 1024)# * x[1]["if-mib"]["ifSpeed"])
						aux_time = x[interface]["time"]
						aux_octets = x[interface]["if-mib"]["ifHCOutOctets"] + x[interface]["if-mib"]["ifHCInOctets"]
						if aux_calc > aux_max_calc:
							aux_max_calc = aux_calc
						aux.append((len(aux) * float(time_interval), aux_calc))
			if len(aux) > 1:
				x,y = getTerminalSize()
				gnuplot.stdin.write("set term dumb %d %d\n" % (x, y-20))
				if aux_max_calc > 0:
					gnuplot.stdin.write("set yrange [0:%f]\n" % aux_max_calc)
				else:
					gnuplot.stdin.write("set yrange [0:1]\n")
				#gnuplot.stdin.write("set xlabel 'kbps'\n")
				#gnuplot.stdin.write("set ylabel 'kbps'\n")
				gnuplot.stdin.write("set title '%s'\n" % interfaces[0][interface]["name"])
				gnuplot.stdin.write("plot '-' using 1:2 title 'kbps' with linespoints \n")
				for i,j in aux:
				   gnuplot.stdin.write("%f %f\n" % (i,j))
				gnuplot.stdin.write("e\n")
				gnuplot.stdin.flush()
			
			if time() - time_start < time_interval:
				sleep(int(time_interval - (time() - time_start)))
			index += 1
	except KeyboardInterrupt:
		writeLog(interfaces, datetime.datetime.fromtimestamp(time()).strftime('%Y-%m-%d_%H:%M:%S')+".log")
		gnuplot.terminate()
		sys.exit(0)

if __name__ == "__main__":
	main()
