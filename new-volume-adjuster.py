#!/usr/bin/env python2
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
import datetime
import time
import math
# From https://github.com/Valodim/python-pulseaudio
sys.path.append(os.path.join(sys.path[0], "python_pulseaudio", "pulseaudio"))
from lib_pulseaudio import * 

# edit to match your sink
# alsa_output.pci-0000_00_14.2.analog-stereo
SINK_NAME = 'alsa_output.pci-0000_00_14.2.analog-stereo'
# METER_RATE = 344
METER_RATE = 10
MAX_SAMPLE_VALUE = 127
DISPLAY_SCALE = 2
MAX_VOLUME = 153
MAX_SPACES = MAX_SAMPLE_VALUE >> DISPLAY_SCALE

class PeakMonitor(object):

    def __init__(self, sink_name, rate):
        self.sink_name = sink_name
        self.rate = rate
        self.input_sinks = {}
        # Wrap callback methods in appropriate ctypefunc instances so
        # that the Pulseaudio C API can call them
        self._context_notify_cb = pa_context_notify_cb_t(self.context_notify_cb)
        self._sink_info_cb = pa_sink_info_cb_t(self.sink_info_cb)\

        self._stream_input_read_cb = pa_stream_request_cb_t(self.stream_input_read_cb)

        self._subscribe = pa_context_subscribe_cb_t(self.subscribe)
        self._subscribe_success = pa_context_success_cb_t(self.subscribe_success)

        # stream_read_cb() puts peak samples into this Queue instance
        self._samples = Queue()

        # Create the mainloop thread and set our context_notify_cb
        # method to be called when there's updates relating to the
        # connection to Pulseaudio
        _mainloop = pa_threaded_mainloop_new()
        _mainloop_api = pa_threaded_mainloop_get_api(_mainloop)
        context = pa_context_new(_mainloop_api, 'volume-adjuster')
        pa_context_set_state_callback(context, self._context_notify_cb, None)
        pa_context_connect(context, None, 0, None)
        pa_threaded_mainloop_start(_mainloop)

    def subscribe(self, context, event_type, idx, *args, **kwargs):
        """
        PA_SUBSCRIPTION_EVENT_SINK = 0,           /**< Event type: Sink */
        PA_SUBSCRIPTION_EVENT_SOURCE = 1,         /**< Event type: Source */
        PA_SUBSCRIPTION_EVENT_SINK_INPUT = 2,     /**< Event type: Sink input */
        PA_SUBSCRIPTION_EVENT_SOURCE_OUTPUT = 3,  /**< Event type: Source output */
        PA_SUBSCRIPTION_EVENT_MODULE = 4,         /**< Event type: Module */
        PA_SUBSCRIPTION_EVENT_CLIENT = 5,         /**< Event type: Client */
        PA_SUBSCRIPTION_EVENT_SAMPLE_CACHE = 6,   /**< Event type: Sample cache item */
        PA_SUBSCRIPTION_EVENT_SERVER = 7,         /**< Event type: Global server change, only occuring with PA_SUBSCRIPTION_EVENT_CHANGE. \since 0.4  */
        PA_SUBSCRIPTION_EVENT_AUTOLOAD = 8,       /**< Event type: Autoload table changes. \since 0.5 */
        PA_SUBSCRIPTION_EVENT_FACILITY_MASK = 15, /**< A mask to extract the event type from an event value */

        PA_SUBSCRIPTION_EVENT_NEW = 0,            /**< A new object was created */
        PA_SUBSCRIPTION_EVENT_CHANGE = 16,        /**< A property of the object was modified */
        PA_SUBSCRIPTION_EVENT_REMOVE = 32,        /**< An object was removed */
        PA_SUBSCRIPTION_EVENT_TYPE_MASK = 16+32"""
        # print "event_type:", event_type, "idx:",idx
        if event_type in (5, 18, 37):
            return
        print "event_type:", event_type, "idx:",idx
        if (event_type & PA_SUBSCRIPTION_EVENT_FACILITY_MASK) == PA_SUBSCRIPTION_EVENT_SINK_INPUT:
            mask = event_type & PA_SUBSCRIPTION_EVENT_TYPE_MASK
            if mask == PA_SUBSCRIPTION_EVENT_NEW:
                print "NEW SINK",idx
                # self._ques["%s" % idx] = Queue()
                o = pa_context_get_sink_input_info(context, idx, self._sink_input_info_cb, None)
                pa_operation_unref(o)

            if mask == PA_SUBSCRIPTION_EVENT_REMOVE:
                print "REMOVE SINK", idx
                print "event_type:", event_type.__repr__()
                print "idx:", idx
                # del self._ques["%s" % idx]
                try:
                    del self.input_sinks["%s" % idx]
                except KeyError:
                    pass

    def subscribe_success(self, *args, **kwargs):
        print "subscribe_success", args

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

            """
            THIS IS HOW TO GET THE MAIN VOLUME
            print "SINK_INFO:",sink_info
            print "SINK_INFO.volume:", sink_info.volume
            pprint.pprint((dir(sink_info.volume)))
            print "sink_info.volume.values:", sink_info.volume.values
            pprint.pprint(sink_info.volume.values)

            print "sink_info.volume.channels:", sink_info.volume.channels
            pprint.pprint((dir(sink_info.volume.channels)))
            pprint.pprint(sink_info.volume.channels)
            print "/ sink_info.volume.channels"

            for val in sink_info.volume.values:
                print "sink_info.volume.values VAL:", val
            """

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
        time.sleep(0.5)
        name = sink_input_info_p.contents.name
        if name == "Event Sound":
            return
        print "NAME:",name
        idx = sink_input_info_p.contents.index

        self.input_sinks["%s" % idx] = LevelMonitorSink(
            context, self.rate, sink_input_info_p, self.monitor_source_name
        )
        print "/"*60

        print "-="*15, "SINK LIST","-="*15
        
        print self.input_sinks


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

class LevelMonitorSink:
    def __init__(self, context, rate, sink_input_info_p, monitor_source_name):
        self.context = context
        self.rate = rate
        self.monitor_source_name = monitor_source_name
        self.sink_input_info_p = sink_input_info_p
        self.name = sink_input_info_p.contents.name
        self.avg = 0
        self.total = 0
        self.vol = 100
        self.count = 0
        self.min = 127
        self.max = 0
        self.history = []
        self.level_history = []
        self.long_history = []
        self.max_history = 2
        self.long_history_length = 10
        self.reset_history_samples = METER_RATE
        self._samples = Queue()

        print "sink_input_info_p:", sink_input_info_p
        print "DIR sink_input_info_p:", 
        pprint.pprint(dir(sink_input_info_p))
        contents = sink_input_info_p.contents
        print "contents:", sink_input_info_p.contents
        # import pdb; pdb.set_trace()

        for v in contents.volume.values:
            print "VAL:", v

        print "(int(contents.volume.values[0]) / 65536.0):", (int(contents.volume.values[0]) / 65536.0)

        self.vol = int(math.ceil((int(contents.volume.values[0]) / 65536.0) * 100))
        print "VOL:", self.vol

        self._stream_input_read_cb = pa_stream_request_cb_t(
            self.stream_input_read_cb)
        print "monitor_source_name:", monitor_source_name
        self.setup_monitor()

    def hard_reset(self):
        self.total = 0
        self.count = 0
        self.avg = 0
        self.min = 127
        self.max = 0
        self.level_history = []

    def stream_input_read_cb(self, stream, length, index_incr):
        if self.name == 'Event Sound':
            print "EVENT SOUND"
            return
        # print self.name
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
            self._samples.put(data[i] - 128)

        pa_stream_drop(stream)
        level = self._samples.get()
        if level < self.min:
            self.min = level
        if level > self.max:
            self.max = level
        self.count += 1
        self.total += level
        self.level_history.append(level)
       
        if self.count > self.reset_history_samples:
            print "#"*30, self.name, "#"*30,"%s" % datetime.datetime.now()
            self.append_history()

    def set_bar_value(self, bar_data, val, fmt):
        pos = str(val / 2)
        bar_data[pos] += [fmt % val]

    def print_bar(self, history):
        if self.name == 'Event Sound':
            print "EVENT SOUND"
            return
        bar_data = {}
        for i in range(-1, 200):
            if self.count >= METER_RATE:
                bar_data[str(i)] = ["-"]
            else:
                bar_data[str(i)] = [" "]

        self.set_bar_value(bar_data, history['min'], '[%3d')
        self.set_bar_value(bar_data, history['avg'], '%3da')
        self.set_bar_value(bar_data, history['max'], '%3d]')
        self.set_bar_value(bar_data, history['vol'], '%3d@')

        
        new_bar = "-"*90
        new_bar2 = "-"*90
        new_bar = new_bar[:48] + "T" + new_bar[48:]
        new_bar2 = new_bar[:48] + "T" + new_bar2[48:]
        min_pos = int(history['min'] / 2) + 2
        new_bar = new_bar[:min_pos-2] + ("[%3d" % history['min'] ) + new_bar[min_pos+2:]
        avg_pos = int(history['avg'] / 2) + 2
        new_bar = new_bar[:avg_pos-2] + ("%3da" % history['avg'] ) + new_bar[avg_pos+2:]

        max_pos = int(history['max']/2) + 2
        new_bar = new_bar[:max_pos-2] + ("%3d]" % history['max'] ) + new_bar[max_pos+2:]

        vol_pos = int(history['vol']/2) + 2
        new_bar2 = new_bar2[:vol_pos-2] + ("%3d@" % history['vol'] ) + new_bar2[vol_pos+2:]

        # self.print_history()
        # pprint.pprint(self.history)
        print self.name, " [",new_bar,"]"
        print self.name, " [",new_bar2,"]"


    def append_history(self):
        if self.name == 'Event Sound':
            return
        self.avg = sum(self.level_history) / len(self.level_history)
        self.history.append({
            "min": self.min,
            "max": self.max,
            "avg": self.avg,
            "vol": self.vol
        })
        self.long_history.append({
            "min": self.min,
            "max": self.max,
            "avg": self.avg,
            "vol": self.vol
        })
        if len(self.history) > self.max_history:
            self.history = self.history[1:]
        if len(self.long_history) > self.long_history_length:
            self.long_history = self.long_history[1:]

        print self.name, "history:", pprint.pformat(self.history)
        
        print self.name, "self.level_history:",len(self.level_history), self.level_history
        print self.name, "self.long_history:", self.long_history
        
        self.hard_reset()
        self.process_history()
        self.long_history_has_changed()
        for h in self.long_history:
            self.print_bar(h)

        if self.name == "Playback Stream":
            print "re-setting monitor"
            self.name = self.sink_input_info_p.contents.name
            # self.sink_input_info_p = sink_input_info_p
            # self.name = sink_input_info_p.contents.name
            
    def long_history_has_changed(self):
        if len(self.long_history) < self.long_history_length:
            return
        for h1 in self.long_history:
            for h2 in self.long_history:
                if h1['min'] != h2['min'] or h1['max'] != h2['max']:
                    print "LONG HISTORY HAS CHANGED"
                    return True
        print "*!"*60
        print "LONG HISTORY HAS NOT CHANGED"
        print "*!"*60
        self.long_history = []
        self.setup_monitor()
        return False

    def process_history(self):
        min_cnt = 0
        max_cnt = 0
        silent_cnt = 0
        too_loud_cnt = 0
        too_soft_cnt = 0
        extreamely_loud_count = 0
        min_too_loud_cnt = 0
        bad_cnt = 0
        adj = 0
        for h in self.history:
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
                adj = -4
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
                adj = -3
                reason = "Way too loud"

            if extreamely_loud_count >= 2:
                adj = -10
                reason = "127 all the way"

            if too_soft_cnt >= 2:
                adj = 2
                reason = "way to soft"

        print self.name, "reason:",reason
        self.adjust_volume(adj)

    def setup_monitor(self):
        sink_input_info = self.sink_input_info_p.contents
        self.index = sink_input_info.index
        self.application_name = sink_input_info.name
        samplespec = pa_sample_spec()
        samplespec.channels = 1
        samplespec.format = PA_SAMPLE_U8
        samplespec.rate = self.rate
        pa_stream = pa_stream_new(self.context, "input-sink %s" % 
            sink_input_info.name, samplespec, None)
        pa_stream_set_monitor_stream(pa_stream, sink_input_info.index);
        pa_stream_set_read_callback(pa_stream,
                                    self._stream_input_read_cb,
                                    sink_input_info.index,
                                    None)

        pa_stream_connect_record(pa_stream,
                                 self.monitor_source_name,
                                 None,
                                 PA_STREAM_PEAK_DETECT)

    def adjust_volume(self, adj):
        if adj == 0:
            return

        vol = self.vol + adj
        if vol > MAX_VOLUME and self.vol != MAX_VOLUME:
            vol = MAX_VOLUME

        if vol <= MAX_VOLUME:
            print "adj:",adj
            new_vol = int(self.convert_vol_to_k(vol))
            exe = "pacmd set-sink-input-volume %s %s" % (self.index, new_vol)
            print "exe:",exe
            subprocess.check_output(exe, shell=True)
            self.vol = vol

    def convert_to_dec(self, vol):
        vol = float(vol)
        return vol / 100

    def convert_vol_to_k(self, vol):
        return (self.convert_to_dec(vol) * 65536)

def main():
    monitor = PeakMonitor(SINK_NAME, METER_RATE)
    while True:
        time.sleep(1)
        

if __name__ == '__main__':
    main()
