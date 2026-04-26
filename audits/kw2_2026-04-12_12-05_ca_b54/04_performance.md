# Performance

## Performance Audit

The provided code is not optimized for performance and has several potential bottlenecks that can be improved upon. Here are some suggestions for improving the performance of the `_crawl` function:

1. **Time complexity**: The current implementation of `_crawl` uses a simple loop to iterate through each page, which has a time complexity of O(n), where n is the number of pages. This can be improved by using a more efficient algorithm such as breadth-first search (BFS) or depth-first search (DFS).
2. **Blocking calls**: The `_crawl` function makes several blocking calls to external APIs, which can slow down the overall performance of the function. To improve this, consider using asynchronous API calls or batching multiple requests together.
3. **Caching**: The current implementation does not make use of caching, which can significantly improve performance by reducing the number of requests made to external APIs. Consider implementing a caching layer to store frequently accessed data.
4. **Parallelization**: The `_crawl` function can be parallelized by dividing the work into smaller tasks that can be executed concurrently on multiple threads or processes. This can help reduce the overall execution time of the function.

Here's an example of how the `_crawl` function could be improved using BFS and asynchronous API calls:
```python
import asyncio
from urllib.parse import urlparse
from aiohttp import ClientSession, web

# ... other imports ...

async def _crawl(url):
    """Crawls the customer site using BFS."""
    async with ClientSession() as session:
        async with session.get(url) as response:
            parsed_url = urlparse(url)
            domain = parsed_url.netloc
            pages = [parsed_url.path]

            while pages:
                tasks = []
                for page in pages:
                    tasks.append(asyncio.ensure_future(_crawl_page(session, domain, page)))
                await asyncio.gather(*tasks)
                pages = [task.result() for task in tasks]

            return pages

async def _crawl_page(session, domain, path):
    """Crawls a single page using BFS."""
    async with session.get(f"https://{domain}{path}") as response:
        parsed_url = urlparse(response.url)
        if parsed_url.netloc != domain:
            return None

        # ... other crawling logic ...
```
This implementation uses the `aiohttp`