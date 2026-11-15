/* SPDX-License-Identifier: GPL-2.0 */
/*
 * Just enough of the kernel for the drawing half of drm_panic.c to build
 * as a normal program. Every kernel header the file includes is a copy
 * of this one (run.sh makes them), except font.h, linux_logo.h and
 * drm_draw_internal.h, which come from the kernel tree as they are.
 */
#ifndef RAYE_PANIC_SIM_KSTUB_H
#define RAYE_PANIC_SIM_KSTUB_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;
typedef int32_t s32;

#define __init
#define __initconst
#define __initdata
#define __ref
#define __read_mostly
#define __packed __attribute__((packed))
#define __maybe_unused __attribute__((unused))
#define MODULE_AUTHOR(x)
#define MODULE_DESCRIPTION(x)
#define MODULE_LICENSE(x)
#define EXPORT_SYMBOL(x)
#define EXPORT_SYMBOL_GPL(x)
#define device_initcall(fn)

#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define DIV_ROUND_UP(n, d) (((n) + (d) - 1) / (d))
#define BITS_PER_BYTE 8
#define min(a, b) ((a) < (b) ? (a) : (b))
#define max(a, b) ((a) > (b) ? (a) : (b))
#define min_t(t, a, b) min((t)(a), (t)(b))
#define max_t(t, a, b) max((t)(a), (t)(b))
#define BUILD_BUG_ON(c) _Static_assert(!(c), #c)
#define WARN_ONCE(c, ...) do { if (c) { fprintf(stderr, __VA_ARGS__); abort(); } } while (0)
#define pr_debug_once(...) do { } while (0)
#define scnprintf(buf, size, ...) \
	({ int __n = snprintf(buf, size, __VA_ARGS__); \
	   __n < 0 ? 0 : ((size_t)__n >= (size) ? (int)(size) - 1 : __n); })

#define PAGE_SHIFT 12
#define PAGE_SIZE (1UL << PAGE_SHIFT)
#define GFP_KERNEL 0
#define ENOMEM 12
static inline void *kmemdup(const void *p, size_t n, int gfp)
{
	void *q = malloc(n);

	(void)gfp;
	if (q)
		memcpy(q, p, n);
	return q;
}
#define kfree(p) free((void *)(p))
#define size_mul(a, b) ((size_t)(a) * (size_t)(b))

/* the sim always draws through set_pixel: no pages, no mapped memory */
struct page { int unused; };
static inline void *kmap_local_page_try_from_panic(struct page *p) { (void)p; abort(); }
static inline void kunmap_local(void *p) { (void)p; }

struct iosys_map { void *vaddr; bool is_iomem; };
static inline void iosys_map_incr(struct iosys_map *m, size_t n) { (void)m; (void)n; abort(); }
static inline bool iosys_map_is_null(const struct iosys_map *m) { return !m->vaddr; }

#define DRM_FORMAT_XRGB8888 0x34325258
#define DRM_FORMAT_MAX_PLANES 4
struct drm_format_info {
	u32 format;
	u8 cpp[DRM_FORMAT_MAX_PLANES];
};

struct drm_scanout_buffer {
	const struct drm_format_info *format;
	struct iosys_map map[DRM_FORMAT_MAX_PLANES];
	struct page **pages;
	unsigned int width;
	unsigned int height;
	unsigned int pitch[DRM_FORMAT_MAX_PLANES];
	void (*set_pixel)(struct drm_scanout_buffer *sb, unsigned int x,
			  unsigned int y, u32 color);
	void *private;
};

struct drm_rect { int x1, y1, x2, y2; };
#define DRM_RECT_INIT(_x, _y, _w, _h) \
	((struct drm_rect){ .x1 = (_x), .y1 = (_y), .x2 = (_x) + (_w), .y2 = (_y) + (_h) })
static inline void drm_rect_init(struct drm_rect *r, int x, int y, int w, int h)
{
	*r = DRM_RECT_INIT(x, y, w, h);
}
static inline void drm_rect_translate(struct drm_rect *r, int dx, int dy)
{
	r->x1 += dx; r->y1 += dy; r->x2 += dx; r->y2 += dy;
}
static inline int drm_rect_width(const struct drm_rect *r) { return r->x2 - r->x1; }
static inline int drm_rect_height(const struct drm_rect *r) { return r->y2 - r->y1; }
static inline bool drm_rect_overlap(const struct drm_rect *a, const struct drm_rect *b)
{
	return a->x2 > b->x1 && b->x2 > a->x1 && a->y2 > b->y1 && b->y2 > a->y1;
}

/* in the kernel these live in drm_draw.c and lib/fonts/fonts.c; sim.c has them */
struct font_desc;
const struct font_desc *find_font(const char *name);
const struct font_desc *get_default_font(int xres, int yres,
					 unsigned long *font_w,
					 unsigned long *font_h);
u32 drm_draw_color_from_xrgb8888(u32 color, u32 format);

#endif
