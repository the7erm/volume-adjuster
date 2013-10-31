#!/usr/bin/env python
# A good portion of this script was taken from
# http://freshfoo.com/blog/pulseaudio_monitoring
import sys
from Queue import Queue
from ctypes import POINTER, c_ubyte, c_void_p, c_ulong, cast
import subprocess
import re
import pprint
import math
import os
 
# From https://github.com/Valodim/python-pulseaudio
sys.path.append(os.path.join(sys.path[0], "python_pulseaudio", "pulseaudio"))
from lib_pulseaudio import * 

# edit to match your sink
# alsa_output.pci-0000_00_14.2.analog-stereo
SINK_NAME = 'alsa_output.pci-0000_00_14.2.analog-stereo'
# METER_RATE = 344
METER_RATE = 20
MAX_SAMPLE_VALUE = 127
DISPLAY_SCALE = 2
MAX_SPACES = MAX_SAMPLE_VALUE >> DISPLAY_SCALE

class PeakMonitor(object):

    def __init__(self, sink_name, rate):
        self.sink_name = sink_name
        self.rate = rate

        # Wrap callback methods in appropriate ctypefunc instances so
        # that the Pulseaudio C API can call them
        self._context_notify_cb = pa_context_notify_cb_t(self.context_notify_cb)
        self._sink_info_cb = pa_sink_info_cb_t(self.sink_info_cb)
        self._stream_read_cb = pa_stream_request_cb_t(self.stream_read_cb)

        # stream_read_cb() puts peak samples into this Queue instance
        self._samples = Queue()

        # Create the mainloop thread and set our context_notify_cb
        # method to be called when there's updates relating to the
        # connection to Pulseaudio
        _mainloop = pa_threaded_mainloop_new()
        _mainloop_api = pa_threaded_mainloop_get_api(_mainloop)
        context = pa_context_new(_mainloop_api, 'peak_demo')
        pa_context_set_state_callback(context, self._context_notify_cb, None)
        pa_context_connect(context, None, 0, None)
        pa_threaded_mainloop_start(_mainloop)

    def __iter__(self):
        while True:
            yield self._samples.get()

    def context_notify_cb(self, context, _):
        state = pa_context_get_state(context)

        if state == PA_CONTEXT_READY:
            print "Pulseaudio connection ready..."
            # Connected to Pulseaudio. Now request that sink_info_cb
            # be called with information about the available sinks.
            o = pa_context_get_sink_info_list(context, self._sink_info_cb, None)
            pa_operation_unref(o)

        elif state == PA_CONTEXT_FAILED :
            print "Connection failed"

        elif state == PA_CONTEXT_TERMINATED:
            print "Connection terminated"

    def sink_info_cb(self, context, sink_info_p, _, __):
        print "sink_info_p:",sink_info_p
        if not sink_info_p:
            return

        sink_info = sink_info_p.contents
        print '-'* 60
        print 'index:', sink_info.index
        print 'name:', sink_info.name
        print 'description:', sink_info.description

        print "sink_info.name:", sink_info.name
        print "self.sink_name:", self.sink_name

        if sink_info.name == self.sink_name:
            # Found the sink we want to monitor for peak levels.
            # Tell PA to call stream_read_cb with peak samples.
            print
            print 'setting up peak recording using', sink_info.monitor_source_name
            print
            samplespec = pa_sample_spec()
            samplespec.channels = 1
            samplespec.format = PA_SAMPLE_U8
            samplespec.rate = self.rate

            pa_stream = pa_stream_new(context, "peak detect demo", samplespec, None)
            pa_stream_set_read_callback(pa_stream,
                                        self._stream_read_cb,
                                        sink_info.index)
            pa_stream_connect_record(pa_stream,
                                     sink_info.monitor_source_name,
                                     None,
                                     PA_STREAM_PEAK_DETECT)

    def stream_read_cb(self, stream, length, index_incr):
        data = c_void_p()
        pa_stream_peek(stream, data, c_ulong(length))
        data = cast(data, POINTER(c_ubyte))
        for i in xrange(length):
            # When PA_SAMPLE_U8 is used, samples values range from 128
            # to 255 because the underlying audio data is signed but
            # it doesn't make sense to return signed peaks.
            self._samples.put(data[i] - 128)
        pa_stream_drop(stream)


class VolumeAdjuster:
    def __init__(self, METER_RATE=METER_RATE):
        self.index_re = re.compile(r"index\:\s+(\d+)")
        # volume: 0: 100%
        self.METER_RATE = METER_RATE
        self.min_value = 127
        self.max_value = 0
        self.count = 0 
        self.upper_silence = 40
        self.lower_silence = 5
        self.too_loud = 115
        self.target = 100
        self.too_soft = 70
        self.one_k = 65536
        self.one_percent = self.one_k * 0.01
        self.total = 0
        self.constant_test = False
        self.vol = -1
        self.idx = -1
        self.last_min_value = 127
        self.last_max_value = 0
        self.target_history_len = 2
        self.history = []
        self.volume_re = re.compile(r"volume\: \d+\:\s+(\d+)\%")
        self.colon_re = re.compile(r"([A-z\ ]+)\:\ (.*)$")
        self.dangling_colon_re = re.compile(r"([A-z\ ]+)\:$")
        self.equal_re = re.compile(r"(.*)\ \=\ (.*)$")
        self.vol_re = re.compile(r"(\d+)\:\s+([\d]+)\%")
        self.digit_re = re.compile(r"^(\d+)$")
        self.double_quote_re = re.compile(r"^\"(.*)\"$")
        self.quote_re = re.compile(r"^\'(.*)\'$")


    def get_sink_info(self):
        sinks = []
        try:
            output = subprocess.check_output("pacmd list-sink-inputs", shell=True)
        except:
            # TODO 
            # return sinks
            return sinks
        sink = {}
        lines = output.split("\n")
        # print output
        inside = ""
        for l in lines:
            colon_match = self.colon_re.search(l)
            if colon_match:
                inside = ""
                k = colon_match.group(1).strip()
                v = colon_match.group(2).strip()
                if k == 'index':
                    if sink != {}:
                        sinks.append(sink)
                    sink = {}
                if k == 'volume':
                    # volume: 0: 100% 1: 100%
                    
                    vol_match = self.vol_re.findall(v)
                    v = {}
                    if vol_match:
                        for channel, value in vol_match:
                            v[channel] = int(value)


                sink[k] = self.convert_value(v)
                
            dangling_match = self.dangling_colon_re.search(l)
            if dangling_match:
                inside = dangling_match.group(1)
                sink[inside] = {}
            if inside:
                matches = self.equal_re.search(l)
                if matches:
                    k = matches.group(1).strip()
                    v = matches.group(2).strip()
                    sink[inside][k] = self.convert_value(v)
        if sink != {}:
            sinks.append(sink)
        # pprint.pprint(sinks)
        return sinks

    def convert_value(self, v):
        if isinstance(v, dict):
            return v
        # print "started:", v.__repr__(), type(v)
        double_quote_match = self.double_quote_re.match(v)
        quote_match = self.quote_re.match(v)
        if double_quote_match:
            v = double_quote_match.group(1)
        elif quote_match:
            v = quote_match.group(1)

        digit_match = self.digit_re.match(v)
        if digit_match:
            v = int(digit_match.group(1))

        # print "ended:", v.__repr__(), type(v)
        return v

    def convert_to_dec(self, vol):
        vol = float(vol)
        return vol / 100

    def convert_vol_to_k(self, vol):
        return (self.convert_to_dec(vol) * 65536)

    def process_sample(self, sample):
        self.count += 1
        self.total += sample
        if sample < self.min_value:
            self.min_value = sample
        if sample > self.max_value:
            self.max_value = sample
        if self.count >= self.METER_RATE:
            self.process_levels()

    def process_levels(self):
        self.sinks = self.get_sink_info()
        if len(self.sinks) == 0:
            self.count = 0
            return
        self.calculate_average()
        self.caclulate_mid_value()
        self.append_history()
        self.process_history()
        self.hard_reset()


    def calculate_average(self):
        self.average = 0
        try:
            self.average = self.total / self.count
        except ZeroDivisionError:
            return
        self.total = 0

    def caclulate_mid_value(self):
        self.mid_value = -1
        try:
            self.mid_value = ((self.max_value - self.min_value) / 2) + self.min_value
        except ZeroDivisionError:
            pass

    def append_history(self):
        this_history = []
        for s in self.sinks:
            this_history.append({
                "min": self.min_value,
                "max": self.max_value,
                "avg": self.average,
                "mid": self.mid_value,
                "idx": s["index"],
                "vol": s['volume']["0"],
                "name": s['properties']['application.name']
            })
        self.history.append(this_history)
        if len(self.history) > self.target_history_len:
            self.history = self.history[1:]
        return

    def hard_reset(self):
        self.count = 0
        self.total = 0
        self.min_value = 127
        self.max_value = 0

    def print_bar(self, adj, reason):
        bar_data = {}
        for i in range(-1, 200):
            if self.count >= self.METER_RATE:
                bar_data[str(i)] = ["-"]
            else:
                bar_data[str(i)] = [" "]

        bar_data[str(self.min_value / 2)] += ['[%3d' % self.min_value]
        bar_data[str(self.mid_value / 2)] += ['%3d|' % self.mid_value]
        bar_data[str(self.average / 2)] += ['%3da' % self.average]
        bar_data[str(self.max_value / 2)] += ['%3d]' % self.max_value]
        for s in self.sinks:
            vol = s['volume']["0"]
            vol_str = str(vol / 2)
            if vol > 127:
                vol_str = str(127 / 2)
            bar_data[vol_str] += ["%3d@" % vol]

        new_bar = ""
        for i in range(0,64):
            key = "%s" % i
            new_bar += " ".join(bar_data[key])

        new_bar = "-"*90
        mid_pos = int(self.mid_value / 2) + 2
        new_bar = new_bar[:mid_pos-2] + ("%3d|" % self.mid_value ) + new_bar[mid_pos+2:]
        min_pos = int(self.min_value / 2) + 2
        new_bar = new_bar[:min_pos-2] + ("[%3d" % self.min_value ) + new_bar[min_pos+2:]
        avg_pos = int(self.average / 2) + 2
        new_bar = new_bar[:avg_pos-2] + ("%3da" % self.average ) + new_bar[avg_pos+2:]

        for s in self.sinks:
            vol = s['volume']["0"]
            vol_pos = int(vol/2) + 2
            new_bar = new_bar[:vol_pos-2] + ("%3d@" % vol ) + new_bar[vol_pos+2:]

        max_pos = int(self.max_value/2) + 2
        new_bar = new_bar[:max_pos-2] + ("%3d]" % self.max_value) + new_bar[max_pos+2:]
        new_bar = new_bar[:48] + "T" + new_bar[48:]

        pprint.pprint(self.history)
        print "nb [",new_bar,"]",
        if adj > 0:
            print "+%s" % adj,reason
        elif adj < 0:
            print adj,reason
        else:
            print "%2d" % adj,reason


    def process_history(self):
        self.adj = 0
        self.reason = ""
        max_cnt = 0
        min_cnt = 0
        silent_cnt = 0
        bad_cnt = 0
        too_loud_cnt = 0
        too_soft_cnt = 0
        min_too_loud_cnt = 0
        extreamely_loud_count = 0
        for sink_history in self.history:
            if len(sink_history) == 0:
                bad_cnt += 1
            try:
                h = sink_history[0]
            except IndexError:
                break
            if h['max'] >= 120:
                too_loud_cnt += 1
            if h['max'] >= 127:
                extreamely_loud_count += 1

            if h['max'] <= 30:
                too_soft_cnt += 1

            if h['max'] >= 110:
                max_cnt += 1
            if h['max'] <= 80:
                min_cnt += 1

            if h['min'] >= 80:
                min_too_loud_cnt += 1

            if h['max'] <= 20 and h['min'] == 0:
                silent_cnt += 1
        
        if silent_cnt >= 1 or bad_cnt:
            adj = 0
            reason = "silent"
            if too_loud_cnt >= 2:
                adj = -3
                reason = "it was silent and, way to loud"
        else:
            if max_cnt >= 1:
                adj = -1
                reason = "max_cnt:%s" % (max_cnt,)
            if min_cnt >= 1:
                adj = 1
                reason = "min_cnt:%s" % min_cnt
            if max_cnt == min_cnt:
                adj = 0
                reason = "equal parts"

            if min_too_loud_cnt >= 2:
                adj = -1
                reason = "min too loud"

            if too_loud_cnt >= 2:
                adj = -4
                reason = "Way too loud"

            if extreamely_loud_count >= 2:
                adj = -8
                reason = "127 all the way"

            if too_soft_cnt >= 2:
                adj = 3
                reason = "way to soft"

        self.print_bar(adj, reason)
        self.adjust_volume(adj)

    def adjust_volume(self, adj):
        if adj == 0:
            return

        for s in self.sinks:
            vol = s['volume']['0']
            idx = s['index']
            vol += adj
            if vol <= 150:
                new_vol = int(self.convert_vol_to_k(vol))
                exe = "pacmd set-sink-input-volume %s %s" % (idx, new_vol)
                # print exe
                if self.count >= METER_RATE and new_vol > 0:
                    subprocess.check_output(exe, shell=True)


def main():
    # pacmd list-sink-inputs | grep index | awk '{print $2}'
    monitor = PeakMonitor(SINK_NAME, METER_RATE)
    volume_adjuster = VolumeAdjuster(METER_RATE=METER_RATE)
    
    for sample in monitor:
        volume_adjuster.process_sample(sample)
        sys.stdout.flush()
        

if __name__ == '__main__':
    main()
