"""
Prometheus metrics reporting for E2E tests using Pushgateway
"""
import time
import uuid
import socket
import platform
import os
from prometheus_client import Counter, Gauge, Histogram, Summary, CollectorRegistry, push_to_gateway

# Pushgateway URL with better detection for Kubernetes environment

# First, check if we're running in Kubernetes by looking for env vars or paths
def is_running_in_kubernetes():
    # Check for standard Kubernetes environment variables
    if os.environ.get('KUBERNETES_SERVICE_HOST') is not None:
        return True
    # Check for Kubernetes service account token file
    if os.path.exists('/var/run/secrets/kubernetes.io/serviceaccount/token'):
        return True
    # All tests failed, not in Kubernetes
    return False

# Set the appropriate Pushgateway URL based on environment
if is_running_in_kubernetes():
    # In Kubernetes, always use the in-cluster service DNS name
    PUSHGATEWAY_URL = 'http://prometheus-pushgateway.hot-e2e-tests:9091'
    print(f"\nRunning in Kubernetes cluster, using service URL: {PUSHGATEWAY_URL}\n")
else:
    # Running locally
    PUSHGATEWAY_URL = os.environ.get('PROMETHEUS_PUSHGATEWAY_URL', 'http://localhost:9091')
    print(f"\nRunning locally, using {PUSHGATEWAY_URL}\n")

class TestMetrics:
    """Simple metrics collector for E2E tests using Prometheus Pushgateway"""
    
    def __init__(self, test_name):
        """Initialize a new metrics collector for a test
        
        Args:
            test_name: Name of the test being executed
        """
        # Create a unique ID for this test run
        self.test_id = str(uuid.uuid4())
        self.test_name = test_name
        self.start_time = time.time()
        self.hostname = socket.gethostname()
        self.steps = {}
        
        # Create a new registry for this test
        self.registry = CollectorRegistry()
        
        # Test duration metric
        self.test_duration = Gauge(
            'hot_e2e_test_duration_seconds', 
            'Duration of E2E test in seconds',
            ['test_id', 'test_name', 'hostname'],
            registry=self.registry
        )
        
        # Step metrics
        self.step_count = Counter(
            'hot_e2e_step_count', 
            'Number of test steps executed',
            ['test_id', 'test_name', 'step_name', 'status'],
            registry=self.registry
        )
        
        self.step_duration = Gauge(
            'hot_e2e_step_duration_seconds', 
            'Duration of each test step in seconds',
            ['test_id', 'test_name', 'step_name'],
            registry=self.registry
        )
    
    def start_step(self, step_name):
        """Record the start of a test step
        
        Args:
            step_name: Name of the step
        """
        self.steps[step_name] = {
            'start_time': time.time(),
            'status': 'running'
        }
        return self
    
    def end_step(self, step_name, status='success', data=None):
        """Record the end of a test step
        
        Args:
            step_name: Name of the step
            status: Status of the step (success or failure)
            data: Additional data about the step
        """
        if step_name not in self.steps:
            self.start_step(step_name)
        
        step = self.steps[step_name]
        step['end_time'] = time.time()
        step['duration'] = step['end_time'] - step['start_time']
        step['status'] = status
        
        if data:
            step['data'] = data
        
        # Record metrics
        self.step_count.labels(
            test_id=self.test_id,
            test_name=self.test_name,
            step_name=step_name,
            status=status
        ).inc()
        
        self.step_duration.labels(
            test_id=self.test_id,
            test_name=self.test_name,
            step_name=step_name
        ).set(step['duration'])
        
        # Push metrics to Pushgateway
        self._push_metrics()
        
        return self
    
    def finish(self):
        """Complete the test and record final metrics"""
        duration = time.time() - self.start_time
        
        # Record total test duration
        self.test_duration.labels(
            test_id=self.test_id,
            test_name=self.test_name,
            hostname=self.hostname
        ).set(duration)
        
        # Final push to Pushgateway
        self._push_metrics()
        
        return duration
    
    def _push_metrics(self):
        """Push metrics to Pushgateway"""
        # Log metrics data before pushing
        print("\n===== METRICS DATA =====")
        print(f"Test ID: {self.test_id}")
        print(f"Test Name: {self.test_name}")
        print(f"Hostname: {self.hostname}")
        print(f"Steps: {list(self.steps.keys())}")
        print(f"Metrics URL: {PUSHGATEWAY_URL}")
        
        # Print all metrics in registry
        for metric in self.registry.collect():
            print(f"\nMetric: {metric.name} ({metric.type})")
            for sample in metric.samples:
                print(f"  - {sample.name}: {sample.value} {sample.labels}")
        print("===== END METRICS =====\n")
        
        try:
            push_to_gateway(
                PUSHGATEWAY_URL,
                job=f'hot_e2e_{self.test_name}',
                registry=self.registry,
                grouping_key={
                    'test_id': self.test_id,
                    'test_name': self.test_name,
                    'hostname': self.hostname
                }
            )
            print(f"Successfully pushed metrics to {PUSHGATEWAY_URL}")
        except Exception as e:
            print(f"Warning: Failed to push metrics to Pushgateway: {str(e)}")
            # Continue execution - we don't want metrics failures to affect tests

# Direct Pushgateway integration - no need for metrics server
