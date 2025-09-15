#!/usr/bin/env python3
"""
TSN FRER Performance Test Suite
Performance evaluation for automotive TSN networks
"""

import time
import socket
import struct
import threading
import statistics
import subprocess
import argparse
from dataclasses import dataclass
from typing import List, Dict, Optional

@dataclass
class TestResults:
    """Test results data structure"""
    test_name: str
    packet_sent: int
    packet_received: int
    packet_lost: int
    loss_rate: float
    avg_latency: float
    max_latency: float
    min_latency: float
    jitter: float
    throughput: float

class FRERTestSuite:
    """Main test suite class"""
    
    def __init__(self, local_ip: str, remote_ip: str):
        self.local_ip = local_ip
        self.remote_ip = remote_ip
        self.test_port = 12345
        self.results: List[TestResults] = []
        
    def setup_frer(self, stream_id: int, sgf_enable: bool, srf_enable: bool):
        """Configure FRER stream"""
        try:
            config_str = f"{stream_id},{int(sgf_enable)},{int(srf_enable)}"
            with open('/proc/frer_config', 'w') as f:
                f.write(config_str)
            print(f"FRER configured: Stream {stream_id}, SGF={sgf_enable}, SRF={srf_enable}")
        except Exception as e:
            print(f"Failed to configure FRER: {e}")
    
    def create_test_packet(self, seq_num: int, timestamp: float) -> bytes:
        """Create test packet with timestamp"""
        # Packet format: [seq_num(4)] [timestamp(8)] [payload(52)]
        packet = struct.pack('!If', seq_num, timestamp)
        packet += b'A' * 52  # Padding to 64 bytes total
        return packet
    
    def send_test_traffic(self, duration: int, rate: int) -> Dict:
        """Send test traffic"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_PRIORITY, 7)  # High priority
        
        interval = 1.0 / rate  # Packet interval in seconds
        sent_packets = 0
        start_time = time.time()
        
        try:
            while time.time() - start_time < duration:
                timestamp = time.time()
                packet = self.create_test_packet(sent_packets, timestamp)
                
                sock.sendto(packet, (self.remote_ip, self.test_port))
                sent_packets += 1
                
                # Rate control
                time.sleep(interval)
                
        except Exception as e:
            print(f"Send error: {e}")
        finally:
            sock.close()
            
        return {
            'sent_packets': sent_packets,
            'duration': time.time() - start_time
        }
    
    def receive_test_traffic(self, duration: int) -> Dict:
        """Receive and analyze test traffic"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((self.local_ip, self.test_port))
        sock.settimeout(1.0)
        
        received_packets = 0
        latencies = []
        sequence_numbers = []
        start_time = time.time()
        
        try:
            while time.time() - start_time < duration + 5:  # Extra 5s for late packets
                try:
                    data, addr = sock.recvfrom(1024)
                    receive_time = time.time()
                    
                    # Parse packet
                    seq_num, send_timestamp = struct.unpack('!If', data[:8])
                    latency = (receive_time - send_timestamp) * 1000  # Convert to ms
                    
                    received_packets += 1
                    latencies.append(latency)
                    sequence_numbers.append(seq_num)
                    
                except socket.timeout:
                    continue
                except Exception as e:
                    print(f"Receive error: {e}")
                    
        finally:
            sock.close()
            
        return {
            'received_packets': received_packets,
            'latencies': latencies,
            'sequence_numbers': sequence_numbers
        }
    
    def calculate_metrics(self, send_result: Dict, recv_result: Dict) -> TestResults:
        """Calculate performance metrics"""
        sent = send_result['sent_packets']
        received = recv_result['received_packets']
        lost = sent - received
        loss_rate = (lost / sent * 100) if sent > 0 else 0
        
        latencies = recv_result['latencies']
        avg_latency = statistics.mean(latencies) if latencies else 0
        max_latency = max(latencies) if latencies else 0
        min_latency = min(latencies) if latencies else 0
        jitter = statistics.stdev(latencies) if len(latencies) > 1 else 0
        
        duration = send_result['duration']
        throughput = (received * 64 * 8) / duration / 1000000  # Mbps
        
        return TestResults(
            test_name="",
            packet_sent=sent,
            packet_received=received,
            packet_lost=lost,
            loss_rate=loss_rate,
            avg_latency=avg_latency,
            max_latency=max_latency,
            min_latency=min_latency,
            jitter=jitter,
            throughput=throughput
        )
    
    def run_latency_test(self, duration: int = 10, rate: int = 100) -> TestResults:
        """Run end-to-end latency test"""
        print(f"Running latency test: {duration}s, {rate}pps")
        
        # Start receiver in separate thread
        recv_result = {}
        def receiver():
            recv_result.update(self.receive_test_traffic(duration))
        
        recv_thread = threading.Thread(target=receiver)
        recv_thread.start()
        
        time.sleep(1)  # Wait for receiver to be ready
        
        # Send traffic
        send_result = self.send_test_traffic(duration, rate)
        
        # Wait for receiver to finish
        recv_thread.join()
        
        # Calculate results
        result = self.calculate_metrics(send_result, recv_result)
        result.test_name = f"Latency Test ({rate}pps)"
        
        return result
    
    def run_reliability_test(self, duration: int = 60) -> TestResults:
        """Run reliability test with link failures"""
        print(f"Running reliability test: {duration}s with link failures")
        
        # Start background traffic
        recv_result = {}
        def receiver():
            recv_result.update(self.receive_test_traffic(duration))
        
        recv_thread = threading.Thread(target=receiver)
        recv_thread.start()
        
        time.sleep(1)
        
        def sender():
            return self.send_test_traffic(duration, 100)
        
        send_thread = threading.Thread(target=sender)
        send_thread.start()
        
        # Simulate link failures
        time.sleep(10)
        print("Simulating primary link failure...")
        subprocess.run(['sudo', 'ip', 'link', 'set', 'eth0', 'down'], 
                      capture_output=True)
        
        time.sleep(5)
        print("Restoring primary link...")
        subprocess.run(['sudo', 'ip', 'link', 'set', 'eth0', 'up'], 
                      capture_output=True)
        
        # Wait for threads to complete
        send_thread.join()
        recv_thread.join()
        
        result = self.calculate_metrics({'sent_packets': 6000, 'duration': duration}, 
                                      recv_result)
        result.test_name = "Reliability Test (with failures)"
        
        return result
    
    def run_throughput_test(self, duration: int = 30) -> List[TestResults]:
        """Run throughput test with varying loads"""
        print(f"Running throughput test: {duration}s")
        
        results = []
        rates = [100, 500, 1000, 5000, 10000]  # packets per second
        
        for rate in rates:
            print(f"Testing at {rate}pps...")
            
            recv_result = {}
            def receiver():
                recv_result.update(self.receive_test_traffic(duration))
            
            recv_thread = threading.Thread(target=receiver)
            recv_thread.start()
            
            time.sleep(1)
            send_result = self.send_test_traffic(duration, rate)
            recv_thread.join()
            
            result = self.calculate_metrics(send_result, recv_result)
            result.test_name = f"Throughput Test ({rate}pps)"
            results.append(result)
            
            time.sleep(2)  # Cool down between tests
            
        return results
    
    def run_frer_comparison(self, duration: int = 30) -> List[TestResults]:
        """Compare performance with and without FRER"""
        print("Running FRER comparison test...")
        
        results = []
        
        # Test without FRER
        print("Testing without FRER...")
        self.setup_frer(100, False, False)
        time.sleep(2)
        
        result_no_frer = self.run_latency_test(duration, 1000)
        result_no_frer.test_name = "Without FRER"
        results.append(result_no_frer)
        
        # Test with FRER
        print("Testing with FRER...")
        self.setup_frer(100, True, True)
        time.sleep(2)
        
        result_with_frer = self.run_latency_test(duration, 1000)
        result_with_frer.test_name = "With FRER"
        results.append(result_with_frer)
        
        return results
    
    def print_results(self, results: List[TestResults]):
        """Print test results in formatted table"""
        print("\n" + "="*80)
        print("TSN FRER Performance Test Results")
        print("="*80)
        
        header = f"{'Test Name':<25} {'Sent':<8} {'Recv':<8} {'Lost':<8} {'Loss%':<8} " \
                f"{'Avg Lat':<10} {'Max Lat':<10} {'Jitter':<10} {'Throughput':<12}"
        print(header)
        print("-" * 80)
        
        for result in results:
            row = f"{result.test_name:<25} " \
                  f"{result.packet_sent:<8} " \
                  f"{result.packet_received:<8} " \
                  f"{result.packet_lost:<8} " \
                  f"{result.loss_rate:<8.3f} " \
                  f"{result.avg_latency:<10.3f} " \
                  f"{result.max_latency:<10.3f} " \
                  f"{result.jitter:<10.3f} " \
                  f"{result.throughput:<12.3f}"
            print(row)
        
        print("-" * 80)
    
    def save_results_csv(self, results: List[TestResults], filename: str):
        """Save results to CSV file"""
        import csv
        
        with open(filename, 'w', newline='') as csvfile:
            fieldnames = ['test_name', 'packet_sent', 'packet_received', 
                         'packet_lost', 'loss_rate', 'avg_latency', 
                         'max_latency', 'min_latency', 'jitter', 'throughput']
            
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for result in results:
                writer.writerow({
                    'test_name': result.test_name,
                    'packet_sent': result.packet_sent,
                    'packet_received': result.packet_received,
                    'packet_lost': result.packet_lost,
                    'loss_rate': result.loss_rate,
                    'avg_latency': result.avg_latency,
                    'max_latency': result.max_latency,
                    'min_latency': result.min_latency,
                    'jitter': result.jitter,
                    'throughput': result.throughput
                })

def main():
    parser = argparse.ArgumentParser(description='TSN FRER Performance Test Suite')
    parser.add_argument('--local-ip', required=True, help='Local IP address')
    parser.add_argument('--remote-ip', required=True, help='Remote IP address')
    parser.add_argument('--test', choices=['latency', 'reliability', 'throughput', 'comparison', 'all'],
                       default='all', help='Test type to run')
    parser.add_argument('--duration', type=int, default=30, help='Test duration in seconds')
    parser.add_argument('--output', help='Output CSV file')
    
    args = parser.parse_args()
    
    test_suite = FRERTestSuite(args.local_ip, args.remote_ip)
    all_results = []
    
    if args.test in ['latency', 'all']:
        result = test_suite.run_latency_test(args.duration, 1000)
        all_results.append(result)
    
    if args.test in ['reliability', 'all']:
        result = test_suite.run_reliability_test(args.duration)
        all_results.append(result)
    
    if args.test in ['throughput', 'all']:
        results = test_suite.run_throughput_test(args.duration)
        all_results.extend(results)
    
    if args.test in ['comparison', 'all']:
        results = test_suite.run_frer_comparison(args.duration)
        all_results.extend(results)
    
    # Print and save results
    test_suite.print_results(all_results)
    
    if args.output:
        test_suite.save_results_csv(all_results, args.output)
        print(f"\nResults saved to {args.output}")

if __name__ == "__main__":
    main()