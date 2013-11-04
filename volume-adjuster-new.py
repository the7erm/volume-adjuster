#!/usr/bin/env python
# A good portion of this script was taken from
# http://freshfoo.com/blog/pulseaudio_monitoring
import sys
from Queue import Queue, Empty
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


        self._stream_input_read_cb = pa_stream_request_cb_t(self.stream_input_read_cb)

        self._subscribe = pa_context_subscribe_cb_t(self.subscribe)
        # pa_context_subscribe_cb_t = CFUNCTYPE(None, POINTER(pa_context), pa_subscription_event_type_t, uint32_t, c_void_p)

        self._subscribe_success = pa_context_success_cb_t(self.subscribe_success)

        # stream_read_cb() puts peak samples into this Queue instance
        self._samples = Queue()
        self._ques = {}

        # Create the mainloop thread and set our context_notify_cb
        # method to be called when there's updates relating to the
        # connection to Pulseaudio
        _mainloop = pa_threaded_mainloop_new()
        _mainloop_api = pa_threaded_mainloop_get_api(_mainloop)
        context = pa_context_new(_mainloop_api, 'peak_demo')
        pa_context_set_state_callback(context, self._context_notify_cb, None)
        pa_context_connect(context, None, 0, None)
        pa_threaded_mainloop_start(_mainloop)

    def subscribe(self, context, event_type, idx, *args, **kwargs):
        if event_type in (5, 18,37):
            return
        # print "event_type:", event_type, "idx:",idx
        if (event_type & PA_SUBSCRIPTION_EVENT_FACILITY_MASK) == PA_SUBSCRIPTION_EVENT_SINK_INPUT:
            mask = event_type & PA_SUBSCRIPTION_EVENT_TYPE_MASK
            if mask == PA_SUBSCRIPTION_EVENT_NEW:
                print "NEW SINK",idx
                self._ques["%s" % idx] = Queue()
                o = pa_context_get_sink_input_info(context, idx, self._sink_input_info_cb, None)
                pa_operation_unref(o)

            if mask == PA_SUBSCRIPTION_EVENT_REMOVE:
                print "REMOVE SINK", idx
                print "event_type:", event_type.__repr__()
                print "idx:", idx
                del self._ques["%s" % idx]

    def subscribe_success(self, *args, **kwargs):
        print "subscribe_success", args

    def __iter__(self):
        while True:
            yield self._samples.get()

    def get_sink_input_samples(self):
        samples = {}
        for idx, q in self._ques.items():
            try:
                samples[idx] = q.get(False)
            except Empty:
                samples[idx] = 0
        return samples

    def context_notify_cb(self, context, _):
        state = pa_context_get_state(context)

        if state == PA_CONTEXT_READY:
            print "Pulseaudio connection ready..."
            # Connected to Pulseaudio. Now request that sink_info_cb
            # be called with information about the available sinks.
            o = pa_context_get_sink_info_list(context, self._sink_info_cb, None)
            pa_operation_unref(o)
            self._sink_input_info_cb = pa_sink_input_info_cb_t(self.sink_input_info_cb)

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

            self.monitor_source_name = sink_info.monitor_source_name

            pa_stream = pa_stream_new(context, "peak detect demo", samplespec, None)
            pa_stream_set_read_callback(pa_stream,
                                        self._stream_read_cb,
                                        sink_info.index)
            pa_stream_connect_record(pa_stream,
                                     sink_info.monitor_source_name,
                                     None,
                                     PA_STREAM_PEAK_DETECT)

            """
            pa_operation* pa_context_subscribe  (   
                pa_context *    c,
                pa_subscription_mask_t  m,
                pa_context_success_cb_t     cb,
                void *  userdata 
            )   """
            # PA_SUBSCRIPTION_EVENT_CHANGE
            # PA_SUBSCRIPTION_MASK_SINK_INPUT
            # PA_SUBSCRIPTION_EVENT_SINK_INPUT
            # PA_SUBSCRIPTION_MASK_SINK
            # PA_STREAM_READY
            # PA_SUBSCRIPTION_MASK_SOURCE_OUTPUT
            # PA_SUBSCRIPTION_EVENT_SINK_INPUT
            pa_context_subscribe(
                context, 
                PA_SUBSCRIPTION_MASK_ALL, 
                self._subscribe_success, None)
            pa_context_set_subscribe_callback(context, self._subscribe, None)

            o = pa_context_get_sink_input_info_list(context, self._sink_input_info_cb, None)
            pa_operation_unref(o)


    def sink_input_info_cb(self, context, sink_input_info_p, _, __):
        print "*"*60
        if not sink_input_info_p:
            print "none", sink_input_info_p
            print "/"*60
            return
        print "="*60
        print "sink_input_info_p.contents.name:", sink_input_info_p.contents.name
        print "sink_input_info_p.contents.index:", sink_input_info_p.contents.index
        sink_input_info = sink_input_info_p.contents
        samplespec = pa_sample_spec()
        samplespec.channels = 1
        samplespec.format = PA_SAMPLE_U8
        samplespec.rate = self.rate
        self._ques["%s" % sink_input_info.index] = Queue()
        pa_stream = pa_stream_new(context, "peak detect demo 2", samplespec, None)
        pa_stream_set_monitor_stream(pa_stream, sink_input_info.index);
        pa_stream_set_read_callback(pa_stream,
                                    self._stream_input_read_cb,
                                    sink_input_info.index,
                                    None)

        pa_stream_connect_record(pa_stream,
                                 self.monitor_source_name,
                                 None,
                                 PA_STREAM_PEAK_DETECT)

        print "/"*60


    def stream_read_cb(self, stream, length, index_incr):
        data = c_void_p()
        pa_stream_peek(stream, data, c_ulong(length))
        data = cast(data, POINTER(c_ubyte))
        for i in xrange(length):
            # When PA_SAMPLE_U8 is used, samples values range from 128
            # to 255 because the underlying audio data is signed but
            # it doesn't make sense to return signed peaks.
            self._samples.put(data[i] - 128)
            # print "stream_read_cb:",data[i]  - 128
        pa_stream_drop(stream)

    def stream_input_read_cb(self, stream, length, index_incr):
        # print "stream:",stream
        # print "index_incr:", index_incr
        data = c_void_p()
        pa_stream_peek(stream, data, c_ulong(length))
        data = cast(data, POINTER(c_ubyte))
        for i in xrange(length):
            # When PA_SAMPLE_U8 is used, samples values range from 128
            # to 255 because the underlying audio data is signed but
            # it doesn't make sense to return signed peaks.
            # self._samples.put(data[i] - 128)
            # print "stream_input_read_cb:",data[i]  - 128
            self._ques["%s" % index_incr].put(data[i] - 128)
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
        self.input_sink_samples = {}
        self.volume_re = re.compile(r"volume\: \d+\:\s+(\d+)\%")
        self.colon_re = re.compile(r"([A-z\ ]+)\:\ (.*)$")
        self.dangling_colon_re = re.compile(r"([A-z\ ]+)\:$")
        self.equal_re = re.compile(r"(.*)\ \=\ (.*)$")
        self.vol_re = re.compile(r"(\d+)\:\s+([\d]+)\%")
        self.digit_re = re.compile(r"^(\d+)$")
        self.double_quote_re = re.compile(r"^\"(.*)\"$")
        self.quote_re = re.compile(r"^\'(.*)\'$")


    def get_sink_input_info(self):
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

    def process_sample(self, sample, input_samples):
        self.count += 1
        self.total += sample

        for k, s in input_samples.iteritems():
            if k not in self.input_sink_samples:
                self.input_sink_samples[k] = {
                    "count": 0,
                    "total": 0,
                    "min": 127,
                    "max": 0
                }
            self.input_sink_samples[k]['count'] += 1
            self.input_sink_samples[k]['total'] += s
            if s < self.input_sink_samples[k]['min']:
                self.input_sink_samples[k]['min'] = s
            if s > self.input_sink_samples[k]['max']:
                self.input_sink_samples[k]['max'] = s

        if sample < self.min_value:
            self.min_value = sample
        if sample > self.max_value:
            self.max_value = sample
        if self.count >= self.METER_RATE:
            self.process_levels()


    def process_levels(self):
        self.sinks = self.get_sink_input_info()
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
            self.average = 0
        
        for k, s in self.input_sink_samples.iteritems():
            try:
                self.input_sink_samples[k]['avg'] = s['total'] / s['count']
            except ZeroDivisionError:
                self.input_sink_samples[k]['avg'] = 0

        if self.average != 0:
            self.total = 0


    def caclulate_mid_value(self):
        self.mid_value = -1
        try:
            self.mid_value = ((self.max_value - self.min_value) / 2) + self.min_value
        except ZeroDivisionError:
            self.mid_value = 0

        for k, s in self.input_sink_samples.iteritems():
            try:
                self.input_sink_samples[k]['mid'] = (
                    (s['max'] - s['min']) / 2) + s['min']
            except ZeroDivisionError:
                self.input_sink_samples[k]['mid'] = 0

    def append_history(self):
        this_history = []
        for s in self.sinks:
            idx = "%s" % s['index']
            try:
                sink_input = self.input_sink_samples[idx]
                this_history.append({
                    "min": sink_input['min'],
                    "max": sink_input['max'],
                    "avg": sink_input['avg'],
                    "mid": sink_input['mid'],
                    "idx": s["index"],
                    "vol": s['volume']["0"],
                    "name": s['properties']['application.name']
                })
            except KeyError, e:
                print "KeyError:",e
        if this_history:
            self.history.append(this_history)
        if len(self.history) > self.target_history_len:
            self.history = self.history[1:]
        return

    def hard_reset(self):
        self.count = 0
        self.total = 0
        self.min_value = 127
        self.max_value = 0
        self.input_sink_samples = {}

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
                adj = -10
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
                try:
                    input_sink_sample = self.input_sink_samples["%s" % idx]
                except KeyError, e:
                    print "KeyError:",e
                    continue
                print "input_sink_sample:", input_sink_sample
                if self.count >= METER_RATE and new_vol > 0 and \
                   input_sink_sample['min'] > 0:
                    subprocess.check_output(exe, shell=True)


def main():
    # pacmd list-sink-inputs | grep index | awk '{print $2}'
    monitor = PeakMonitor(SINK_NAME, METER_RATE)
    volume_adjuster = VolumeAdjuster(METER_RATE=METER_RATE)
    
    for sample in monitor:
        input_samples = monitor.get_sink_input_samples()
        volume_adjuster.process_sample(sample, input_samples)
        #  print "input_samples:", input_samples
        sys.stdout.flush()
        

if __name__ == '__main__':
    main()
