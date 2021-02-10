from datetime import datetime, timedelta
from multiprocessing.connection import Client, Listener
from multiprocessing import Process, Pipe
from collections import deque
from math import nan
import argparse
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import matplotlib


def server(conn, serial_port):
    import serial
    tty = serial.Serial(serial_port, 2000000, timeout=None)
    while True:
        raw_line = tty.readline()
        try:
            raw_data = raw_line.decode('ascii').split(',')
            if len(raw_data) != 5:
                print(f"Received garbage data {raw_line}")
                continue
            time = datetime.utcnow()
            tip = int(raw_data[0])
            handle_x10 = int(raw_data[1])
            power_x10 = int(raw_data[2])
            pwm = int(raw_data[3])
            tip_raw_uv = int(raw_data[4])
        except Exception as ex:
            print(
                f"Received garbage data {raw_line} which caused exception: {ex}")
            continue
        conn.send({
            'time': time,
            'tip': tip,
            'handle_x10': handle_x10,
            'power_x10': power_x10,
            'pwm': pwm,
            'tip_raw_uv': tip_raw_uv,
        })


def client(conn):
    d_time = deque()
    d_tip = deque()
    d_handle = deque()
    d_tipraw = deque()
    d_power = deque()
    d_pwm = deque()

    fig: matplotlib.figure.Figure
    ax: matplotlib.axes.Axes
    ax1: matplotlib.axes.Axes
    fig, (ax, ax1) = plt.subplots(2, 1, sharex=True,
                                  gridspec_kw={'height_ratios': [2, 1]})
    ax_2 = ax.twinx()
    ax1_2 = ax1.twinx()
    # plt.ion()
    ax.set_xlabel('Time')

    ax.set_ylabel('Temp (°C)')
    ax.set_ylim(0, 450)
    l_tip, = ax.plot([], '-r', label="Tip")
    l_handle, = ax.plot([], '-g', label="Handle")
    ax.legend(loc='upper left')

    ax_2.set_ylabel('Thermocouple Raw (μV)')
    ax_2.set_ylim(0, 20000)
    l_tipraw, = ax_2.plot([], '-c', label="Tip Raw")
    ax_2.yaxis.get_label().set_color(l_tipraw.get_color())
    ax_2.legend(loc='upper right')

    ax1.set_ylabel('Power (W)')
    l_power, = ax1.plot([], '-b', label="Power")
    ax1.yaxis.get_label().set_color(l_power.get_color())

    ax1_2.set_ylabel('PWM [0-255]')
    l_pwm, = ax1_2.plot([], '-y', label="PWM")
    ax1_2.yaxis.get_label().set_color(l_pwm.get_color())
    ax1_2.set_ylim(-5, 260)
    ax1_2.set_yticks([0, 32, 64, 96, 128, 160, 192, 224, 256])

    ax.grid()
    ax1.grid()
    plt.subplots_adjust(hspace=.0)

    def run(_i):
        now = datetime.utcnow()
        cutoff = now - timedelta(seconds=30)

        while len(d_time) > 0 and d_time[0] < cutoff:
            d_time.popleft()
            d_tip.popleft()
            d_handle.popleft()
            d_tipraw.popleft()
            d_power.popleft()
            d_pwm.popleft()

        while conn.poll():
            item = conn.recv()
            if len(d_time) > 0 and (item['time'] - d_time[len(d_time) - 1]).total_seconds() >= 1:
                d_time.append(item)
                d_tip.append(nan)
                d_handle.append(nan)
                d_tipraw.append(nan)
                d_power.append(nan)
                d_pwm.append(nan)
            d_time.append(item['time'])
            d_tip.append(item['tip'])
            d_handle.append(item['handle_x10'] / 10)
            d_tipraw.append(item['tip_raw_uv'])
            d_power.append(item['power_x10'] / 10)
            d_pwm.append(item['pwm'])

        l_tip.set_data(d_time, d_tip)
        l_handle.set_data(d_time, d_handle)
        l_tipraw.set_data(d_time, d_tipraw)
        l_power.set_data(d_time, d_power)
        l_pwm.set_data(d_time, d_pwm)

        ax.set_xlim(cutoff, now)
        ax1.relim()
        ax1.autoscale(axis='y')

        return [l_tip, l_handle, l_tipraw, l_power, l_pwm]

    ani = animation.FuncAnimation(fig, run, interval=200, blit=False)
    plt.show(block=True)
    conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("command", help="Action - server reads from serial port, client plots data, leave out to run both",
                        nargs='?', choices=["server", "client", "all"], default="all")
    parser.add_argument(
        "serial_port", help="The serial port to use, only used for server. Default: /dev/ttyAMA0", nargs='?', default="/dev/ttyAMA0")
    parser.add_argument(
        "--addr", help="The address to connect/bind to, not used if running both. Default: 0.0.0.0 for server and 127.0.0.1 for client")
    parser.add_argument(
        "--port", help="The port to connect/bind to, not used if running both. Default: 3000", type=int, default=3000)

    args = parser.parse_args()

    if args.command == "server":
        address = (args.addr if args.addr is not None else "0.0.0.0", args.port)
        print(f"Listening on {address}")
        listener = Listener(address, family='AF_INET', authkey=b'IronOS')
        conn = listener.accept()
        listener.close()
        server(conn, args.serial_port)
    elif args.command == "client":
        address = (args.addr if args.addr is not None else "127.0.0.1", args.port)
        print(f"Connecting to {address}")
        conn = Client(address, family='AF_INET', authkey=b'IronOS')
        print(f"Connected!")
        client(conn)
    elif args.command == "all":
        pipe_a, pipe_b = Pipe()
        p = Process(target=server, args=(pipe_a, args.serial_port))
        p.start()
        try:
            client(pipe_b)
        finally:
            p.join(3)
            if p.is_alive():
                p.terminate()
    else:
        parser.print_help()
