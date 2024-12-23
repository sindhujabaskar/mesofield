import queue

class DataManager:
    '''Singleton class for managing data shared between threads.
    
    This class provides a thread-safe way to share data between threads using a queue.
    
    *Example Usage*:
        ```python
        from data_manager import DataManager
        import threading
        import time

        def sample_real_time_data():
            data_manager = DataManager()
            while True:
             # Sleep or wait based on your sampling rate
                time.sleep(1)  # For example, sample every 1 second

                # Process all data currently in the queue
                while not data_manager.data_queue.empty():
                    try:
                        data_point = data_manager.data_queue.get_nowait()
                        # Process data_point
                        print(f"Sampled data: {data_point}")
                    except queue.Empty:
                        break

        # Run in a separate thread if needed
        sampling_thread = threading.Thread(target=sample_real_time_data)
        sampling_thread.start()
        
        ```
    '''
    _instance = None
    _queue = queue.Queue()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DataManager, cls).__new__(cls)
        return cls._instance

    @property
    def data_queue(self):
        return self._queue


