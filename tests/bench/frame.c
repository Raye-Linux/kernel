/* A game-like loop: every 16.7 ms (60 Hz) it does a fixed amount of CPU
 * work and records how long after the frame start the work was done.
 * Run it next to a CPU load to see how the scheduler treats it.
 *   cc -O2 -o frame frame.c && ./frame 4000 600
 * prints p50, p99, p99.9 and max in microseconds, and the frames that
 * missed 16.7 ms.
 */
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

static long long now_ns(clockid_t c)
{
	struct timespec t;

	clock_gettime(c, &t);
	return t.tv_sec * 1000000000LL + t.tv_nsec;
}

static int cmp(const void *a, const void *b)
{
	long long x = *(const long long *)a, y = *(const long long *)b;

	return (x > y) - (x < y);
}

int main(int argc, char **argv)
{
	long long work_ns = (argc > 1 ? atoll(argv[1]) : 4000) * 1000;
	int frames = argc > 2 ? atoi(argv[2]) : 600;
	const long long period = 16666667;
	long long *lat = calloc(frames, sizeof(*lat));
	struct timespec next;
	int missed = 0;

	clock_gettime(CLOCK_MONOTONIC, &next);
	for (int i = 0; i < frames; i++) {
		long long start, cpu0;

		next.tv_nsec += period;
		while (next.tv_nsec >= 1000000000) {
			next.tv_nsec -= 1000000000;
			next.tv_sec++;
		}
		clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &next, NULL);
		start = next.tv_sec * 1000000000LL + next.tv_nsec;
		/* work counted in CPU time, so it is the same amount every frame */
		cpu0 = now_ns(CLOCK_THREAD_CPUTIME_ID);
		while (now_ns(CLOCK_THREAD_CPUTIME_ID) - cpu0 < work_ns)
			;
		lat[i] = now_ns(CLOCK_MONOTONIC) - start;
		if (lat[i] > period)
			missed++;
	}
	qsort(lat, frames, sizeof(*lat), cmp);
	printf("%lld %lld %lld %lld missed %d\n", lat[frames / 2] / 1000,
	       lat[frames * 99 / 100] / 1000, lat[frames * 999 / 1000] / 1000,
	       lat[frames - 1] / 1000, missed);
	return 0;
}
