/* Opens and closes an input device n times and prints the time it took.
 *   cc -O2 -o evclose evclose.c && sudo ./evclose /dev/input/event0 1000
 */
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <unistd.h>

int main(int argc, char **argv)
{
	const char *path = argc > 1 ? argv[1] : "/dev/input/event0";
	int n = argc > 2 ? atoi(argv[2]) : 1000;
	struct timespec a, b;

	clock_gettime(CLOCK_MONOTONIC, &a);
	for (int i = 0; i < n; i++) {
		int fd = open(path, O_RDONLY);
		if (fd < 0) {
			perror(path);
			return 1;
		}
		close(fd);
	}
	clock_gettime(CLOCK_MONOTONIC, &b);
	printf("%d open/close of %s: %.1f ms\n", n, path,
	       (b.tv_sec - a.tv_sec) * 1e3 + (b.tv_nsec - a.tv_nsec) / 1e6);
	return 0;
}
