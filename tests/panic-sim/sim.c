// SPDX-License-Identifier: GPL-2.0
/*
 * Draws the "user" crash screen of the patched drm_panic.c into a
 * picture, the way the kernel would draw it on a framebuffer:
 *
 *   sim <width> <height> <out.ppm> [logo|nologo] [description]
 *
 * run.sh builds it from a kernel tree. It stops (abort) on any pixel
 * written outside the screen, and ASan/UBSan catch reads outside the
 * font or the picture.
 */
#include <linux/types.h>
#include <linux/font.h>
#include <linux/linux_logo.h>

#define CONFIG_LOGO 1
#define CONFIG_DRM_PANIC_FOREGROUND_COLOR 0xf3eaff
#define CONFIG_DRM_PANIC_BACKGROUND_COLOR 0x2a1052

#include "drm_panic_cut.c"

static bool with_logo = true;

const struct linux_logo *fb_find_logo(int depth)
{
	return with_logo && depth >= 1 ? &logo_linux_mono : NULL;
}

const struct font_desc *find_font(const char *name)
{
	if (!strcmp(name, font_vga_8x16.name))
		return &font_vga_8x16;
	if (!strcmp(name, font_ter_16x32.name))
		return &font_ter_16x32;
	return NULL;
}

const struct font_desc *get_default_font(int xres, int yres,
					 unsigned long *font_w,
					 unsigned long *font_h)
{
	(void)xres; (void)yres; (void)font_w; (void)font_h;
	return &font_vga_8x16;
}

u32 drm_draw_color_from_xrgb8888(u32 color, u32 format)
{
	if (format != DRM_FORMAT_XRGB8888)
		abort();
	return color & 0xffffff;
}

/* the sim draws through set_pixel only */
#define NOT_HERE(name, ...) void name(__VA_ARGS__) { abort(); }
NOT_HERE(drm_draw_blit16, struct iosys_map *d, unsigned int dp, const u8 *s,
	 unsigned int sp, unsigned int h, unsigned int w, unsigned int sc, u16 c)
NOT_HERE(drm_draw_blit24, struct iosys_map *d, unsigned int dp, const u8 *s,
	 unsigned int sp, unsigned int h, unsigned int w, unsigned int sc, u32 c)
NOT_HERE(drm_draw_blit32, struct iosys_map *d, unsigned int dp, const u8 *s,
	 unsigned int sp, unsigned int h, unsigned int w, unsigned int sc, u32 c)
NOT_HERE(drm_draw_fill16, struct iosys_map *d, unsigned int dp,
	 unsigned int h, unsigned int w, u16 c)
NOT_HERE(drm_draw_fill24, struct iosys_map *d, unsigned int dp,
	 unsigned int h, unsigned int w, u32 c)
NOT_HERE(drm_draw_fill32, struct iosys_map *d, unsigned int dp,
	 unsigned int h, unsigned int w, u32 c)

static u32 *screen;

static void put(struct drm_scanout_buffer *sb, unsigned int x, unsigned int y,
		u32 color)
{
	if (x >= sb->width || y >= sb->height) {
		fprintf(stderr, "pixel outside the screen: %u,%u\n", x, y);
		abort();
	}
	screen[(size_t)y * sb->width + x] = color;
}

int main(int argc, char **argv)
{
	static const struct drm_format_info xrgb = {
		.format = DRM_FORMAT_XRGB8888, .cpp = { 4 },
	};
	struct drm_scanout_buffer sb = { .format = &xrgb, .set_pixel = put };
	const char *description = "sysrq triggered crash\n";
	size_t i, n;
	FILE *f;

	if (argc < 4) {
		fprintf(stderr, "usage: sim <width> <height> <out.ppm> [logo|nologo] [description]\n");
		return 2;
	}
	sb.width = (unsigned int)atoi(argv[1]);
	sb.height = (unsigned int)atoi(argv[2]);
	if (!sb.width || !sb.height || sb.width > 8192 || sb.height > 8192)
		return 2;
	if (argc > 4 && !strcmp(argv[4], "nologo"))
		with_logo = false;
	if (argc > 5)
		description = argv[5];

	n = (size_t)sb.width * sb.height;
	screen = malloc(n * sizeof(*screen));
	if (!screen)
		return 1;
	/* a colour the crash screen never uses: shows any pixel left unpainted */
	for (i = 0; i < n; i++)
		screen[i] = 0x00ff00;

	if (drm_panic_setup_logo())
		return 1;
	drm_panic_set_description(description);
	draw_panic_screen_user(&sb);

	f = fopen(argv[3], "wb");
	if (!f)
		return 1;
	fprintf(f, "P6\n%u %u\n255\n", sb.width, sb.height);
	for (i = 0; i < n; i++) {
		fputc(screen[i] >> 16 & 0xff, f);
		fputc(screen[i] >> 8 & 0xff, f);
		fputc(screen[i] & 0xff, f);
	}
	return fclose(f) ? 1 : 0;
}
