/* libg15render.so on this system was built with FreeType/TTF support
   compiled in, which adds extra fields to g15canvas (see the #ifdef
   TTF_SUPPORT block in the header). Without defining this here too, our
   compilation sees a SMALLER g15canvas struct than the library actually
   writes to -- g15r_initCanvas() then writes past the end of our
   stack-allocated struct. This was a latent bug in the original code too
   (it just happened to land on harmless stack padding); confirmed via
   AddressSanitizer + a stack-protector trip while adding v1.1 features. */
#define TTF_SUPPORT
#include <ft2build.h>
#include FT_FREETYPE_H
#include <libg15render.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <time.h>
#include <sys/statvfs.h>
#include <sys/stat.h>
#include <dirent.h>

/* Exact port of libg15's dumpPixmapIntoLCDFormat(): converts libg15render's
   row-major MSB-first bitmap into the LCD's vertical "page" wire format. */
static void dump_to_lcd_format(unsigned char *lcd_buffer, unsigned char const *data) {
    unsigned int output_offset = 32;
    unsigned int base_offset = 0;
    unsigned int curr_row, curr_col;

    for (curr_row = 0; curr_row < 6; ++curr_row) {
        for (curr_col = 0; curr_col < 160; ++curr_col) {
            unsigned int bit = curr_col % 8;
            lcd_buffer[output_offset] =
                (((data[base_offset]        << bit) & 0x80) >> 7) |
                (((data[base_offset + 20]   << bit) & 0x80) >> 6) |
                (((data[base_offset + 40]   << bit) & 0x80) >> 5) |
                (((data[base_offset + 60]   << bit) & 0x80) >> 4) |
                (((data[base_offset + 80]   << bit) & 0x80) >> 3) |
                (((data[base_offset + 100]  << bit) & 0x80) >> 2) |
                (((data[base_offset + 120]  << bit) & 0x80) >> 1) |
                (((data[base_offset + 140]  << bit) & 0x80) >> 0);
            ++output_offset;
            if (bit == 7) base_offset++;
        }
        base_offset += 160 - 20;
    }
}

static void send_frame(g15canvas *canvas) {
    unsigned char report[992];
    memset(report, 0, 32);
    report[0] = 0x03;
    dump_to_lcd_format(report, canvas->buffer);

    /* Stable symlink from the udev rule (99-g510-lcd.rules) -- the raw
       hidraw number can shift across reboots/replugs, this doesn't. */
    FILE *f = fopen("/dev/g510-lcd", "wb");
    if (!f) { perror("open /dev/g510-lcd"); return; }
    fwrite(report, 1, 992, f);
    fclose(f);
}

/* Renders the canvas to a plain PPM image instead of the real hardware --
   used by --preview so the GUI's editor pane shows pixel-for-pixel exactly
   what the real LCD would show, using the identical drawing code path.
   Colors are tinted to evoke the real G510's green-on-black panel. */
static void write_ppm(g15canvas *c, const char *path) {
    FILE *f = fopen(path, "wb");
    if (!f) { perror("open preview output"); return; }
    fprintf(f, "P6\n%d %d\n255\n", G15_LCD_WIDTH, G15_LCD_HEIGHT);
    for (int y = 0; y < G15_LCD_HEIGHT; y++) {
        for (int x = 0; x < G15_LCD_WIDTH; x++) {
            int lit = g15r_getPixel(c, x, y) == G15_COLOR_BLACK;
            unsigned char px[3];
            if (lit) { px[0] = 20; px[1] = 40; px[2] = 15; }
            else     { px[0] = 190; px[1] = 214; px[2] = 145; }
            fwrite(px, 1, 3, f);
        }
    }
    fclose(f);
}

/* --- stat readers --- */

static void read_cpu_totals(unsigned long long *idle, unsigned long long *total) {
    FILE *f = fopen("/proc/stat", "r");
    unsigned long long user, nice, sys, idl, iowait, irq, softirq, steal;
    fscanf(f, "cpu %llu %llu %llu %llu %llu %llu %llu %llu",
           &user, &nice, &sys, &idl, &iowait, &irq, &softirq, &steal);
    fclose(f);
    *idle = idl + iowait;
    *total = user + nice + sys + idl + iowait + irq + softirq + steal;
}

static double get_cpu_percent(void) {
    static unsigned long long prev_idle = 0, prev_total = 0;
    unsigned long long idle, total;
    read_cpu_totals(&idle, &total);
    unsigned long long dt = total - prev_total;
    unsigned long long di = idle - prev_idle;
    double pct = (dt > 0) ? (100.0 * (double)(dt - di) / (double)dt) : 0.0;
    prev_idle = idle; prev_total = total;
    return pct;
}

/* returns used/total RAM in KB via MemTotal/MemAvailable */
static void get_ram_kb(long *used_kb, long *total_kb) {
    FILE *f = fopen("/proc/meminfo", "r");
    char label[64];
    long value;
    long mem_total = 0, mem_avail = 0;
    char line[256];
    while (fgets(line, sizeof(line), f)) {
        if (sscanf(line, "%63s %ld", label, &value) == 2) {
            if (strcmp(label, "MemTotal:") == 0) mem_total = value;
            else if (strcmp(label, "MemAvailable:") == 0) mem_avail = value;
        }
    }
    fclose(f);
    *total_kb = mem_total;
    *used_kb = mem_total - mem_avail;
}

static int get_cpu_temp_c(void) {
    FILE *f = fopen("/sys/class/hwmon/hwmon3/temp1_input", "r");
    if (!f) return -1;
    int millideg = 0;
    fscanf(f, "%d", &millideg);
    fclose(f);
    return millideg / 1000;
}

static void get_vram_bytes(unsigned long long *used, unsigned long long *total) {
    FILE *f;
    *used = 0; *total = 0;
    f = fopen("/sys/class/drm/card1/device/mem_info_vram_used", "r");
    if (f) { fscanf(f, "%llu", used); fclose(f); }
    f = fopen("/sys/class/drm/card1/device/mem_info_vram_total", "r");
    if (f) { fscanf(f, "%llu", total); fclose(f); }
}

static void format_gb(unsigned long long bytes, char *out, size_t outlen) {
    snprintf(out, outlen, "%.1fG", bytes / (1024.0 * 1024.0 * 1024.0));
}

static double get_cpu_ghz(void) {
    FILE *f = fopen("/proc/cpuinfo", "r");
    if (!f) return 0.0;
    char line[256];
    double mhz = 0.0;
    while (fgets(line, sizeof(line), f)) {
        if (strncmp(line, "cpu MHz", 7) == 0) {
            sscanf(strchr(line, ':') + 1, "%lf", &mhz);
            break;
        }
    }
    fclose(f);
    return mhz / 1000.0;
}

/* --- Phase 2 sensors (v1.1) --- */

static int read_hwmon_temp_c(const char *path) {
    FILE *f = fopen(path, "r");
    if (!f) return -1;
    int millideg = 0;
    fscanf(f, "%d", &millideg);
    fclose(f);
    return millideg / 1000;
}

static double get_gpu_percent(void) {
    FILE *f = fopen("/sys/class/drm/card1/device/gpu_busy_percent", "r");
    if (!f) return -1;
    int v = 0;
    fscanf(f, "%d", &v);
    fclose(f);
    return (double)v;
}

static double get_swap_percent(void) {
    FILE *f = fopen("/proc/meminfo", "r");
    if (!f) return -1;
    char label[64]; long value;
    long swap_total = 0, swap_free = 0;
    char line[256];
    while (fgets(line, sizeof(line), f)) {
        if (sscanf(line, "%63s %ld", label, &value) == 2) {
            if (strcmp(label, "SwapTotal:") == 0) swap_total = value;
            else if (strcmp(label, "SwapFree:") == 0) swap_free = value;
        }
    }
    fclose(f);
    if (swap_total <= 0) return 0.0; /* no swap configured -- not an error */
    return 100.0 * (swap_total - swap_free) / swap_total;
}

/* Returns -1 if the path isn't mounted right now (e.g. removable "frigider"
   drive unplugged) instead of guessing or crashing. */
static double get_disk_percent(const char *path) {
    struct statvfs st;
    if (statvfs(path, &st) != 0) return -1;
    if (st.f_blocks == 0) return -1;
    return 100.0 * (st.f_blocks - st.f_bfree) / st.f_blocks;
}

static double get_uptime_hours(void) {
    FILE *f = fopen("/proc/uptime", "r");
    if (!f) return 0.0;
    double up = 0.0;
    fscanf(f, "%lf", &up);
    fclose(f);
    return up / 3600.0;
}

/* Network throughput is delta-based, so it's computed exactly once per
   frame (regardless of how many elements reference it) into these cached
   globals -- calling the delta logic per-element would corrupt the deltas. */
static double g_net_down_kbps = 0, g_net_up_kbps = 0;

static void update_net_speed(void) {
    static unsigned long long prev_rx = 0, prev_tx = 0;
    static time_t prev_time = 0;
    unsigned long long rx = 0, tx = 0;
    FILE *f = fopen("/proc/net/dev", "r");
    if (f) {
        char line[512];
        while (fgets(line, sizeof(line), f)) {
            char *iface = strstr(line, "wlp4s0:");
            if (iface) {
                unsigned long long r, t;
                sscanf(iface + 7, "%llu %*u %*u %*u %*u %*u %*u %*u %llu", &r, &t);
                rx = r; tx = t;
                break;
            }
        }
        fclose(f);
    }
    time_t now = time(NULL);
    double dt = prev_time > 0 ? difftime(now, prev_time) : 0;
    if (dt > 0 && prev_rx > 0) {
        g_net_down_kbps = (rx - prev_rx) / 1024.0 / dt;
        g_net_up_kbps = (tx - prev_tx) / 1024.0 / dt;
    }
    prev_rx = rx; prev_tx = tx; prev_time = now;
}

static void format_kbps(double kbps, char *out, size_t outlen) {
    if (kbps > 1024.0) snprintf(out, outlen, "%.1fM", kbps / 1024.0);
    else snprintf(out, outlen, "%.0fK", kbps);
}

/* --- layout --- */

#define ROW_CPU  3
#define ROW_RAM  33
#define ROW_VRAM 23
#define ROW_TEMP 13
#define BAR_H    4

#define LABEL_X  6
#define PCT_X    35
#define BAR_X1   62
#define BAR_X2   122
#define AMT_X    125

/* Slim, borderless bar: a 1px baseline marks full scale, a filled block
   on top shows the current value. No boxed outline (elegant, not "fat"). */
static void draw_slim_bar(g15canvas *c, int x1, int x2, int y, int h, int pct) {
    if (pct < 0) pct = 0;
    if (pct > 100) pct = 100;
    g15r_drawLine(c, x1, y + h + 1, x2, y + h + 1, G15_COLOR_BLACK);
    int fill_x2 = x1 + (int)((x2 - x1) * (pct / 100.0));
    if (fill_x2 > x1) {
        g15r_pixelBox(c, x1, y, fill_x2, y + h, G15_COLOR_BLACK, 1, G15_PIXEL_FILL);
    }
}

/* Labels: Eurostile Bold (custom-converted, matches original G510 look).
   Numbers: the library's own built-in bitmap font -- it was purpose-built
   for this exact tiny resolution, so it stays legible where converted
   TTFs keep garbling at 6-8px. */
static g15font *label_font = NULL;

#define LABEL_Y_OFFSET 3 /* Eurostile's metrics sit higher than the number font's */

/* PROJECT_DIR is passed at compile time by install.sh/rebuild.sh
   (-DPROJECT_DIR='"'$DIR'"') so this file doesn't hardcode a username
   or a specific checkout location. Both scripts always pass it, so
   there's no real case where a fallback value is needed -- and a
   fallback would have to be either someone's actual real path (which
   defeats the whole point) or a made-up one that fails in a confusing
   way at runtime. Failing loudly at COMPILE time instead: hand-compile
   this file directly and you get a clear error telling you what to do,
   not a silently-wrong path or a random "file not found" later. */
#ifndef PROJECT_DIR
#error "PROJECT_DIR not defined -- compile via install.sh or scripts/rebuild.sh, or pass -DPROJECT_DIR='\"/your/checkout/path\"' yourself"
#endif
#define FONT_PATH PROJECT_DIR "/fonts/lcd-label-8.fnt"

/* Your own custom-screens config and imported images live under
   ~/.local/share/g510-lcd, independent of where the program itself is
   installed from (a dev checkout via install.sh, or a real package
   under a fixed /usr/lib/g510-lcd) -- so a package upgrade (root-owned,
   read-only /usr/lib) never touches what you've actually configured.
   Mirrors button_log_path() in g510_lcd_buttons.c. On first run after
   upgrading from a version that stored these directly under
   PROJECT_DIR, migrate the old files over once rather than silently
   showing "not configured" on a screen that was actually already set
   up -- migrate_file_if_needed()/migrate_dir_if_needed() are no-ops
   whenever there's nothing old to migrate (a real package install,
   or a dev checkout that's already been migrated once). */
/* Plain mkdir() only creates one level -- ~/.local/share doesn't
   necessarily exist yet on every system (confirmed the hard way: an
   isolated test with a fresh, empty $HOME silently failed to create
   ~/.local/share/g510-lcd because mkdir() can't create the missing
   ~/.local and ~/.local/share parents in one call). Walks the path
   one "/"-separated component at a time, creating each as needed. */
static void mkdir_p(const char *path) {
    char tmp[256];
    snprintf(tmp, sizeof(tmp), "%s", path);
    for (char *p = tmp + 1; *p; p++) {
        if (*p == '/') {
            *p = 0;
            mkdir(tmp, 0755);
            *p = '/';
        }
    }
    mkdir(tmp, 0755);
}

static void migrate_file_if_needed(const char *old_path, const char *new_path) {
    FILE *already = fopen(new_path, "r");
    if (already) { fclose(already); return; }
    FILE *src = fopen(old_path, "r");
    if (!src) return;
    FILE *dst = fopen(new_path, "w");
    if (!dst) { fclose(src); return; }
    char buf[4096];
    size_t n;
    while ((n = fread(buf, 1, sizeof(buf), src)) > 0) fwrite(buf, 1, n, dst);
    fclose(src);
    fclose(dst);
}

static void migrate_dir_if_needed(const char *old_dir, const char *new_dir) {
    DIR *d = opendir(old_dir);
    if (!d) return;
    mkdir_p(new_dir);
    struct dirent *entry;
    while ((entry = readdir(d)) != NULL) {
        if (entry->d_name[0] == '.') continue;
        char old_path[512], new_path[512];
        snprintf(old_path, sizeof(old_path), "%s/%s", old_dir, entry->d_name);
        snprintf(new_path, sizeof(new_path), "%s/%s", new_dir, entry->d_name);
        migrate_file_if_needed(old_path, new_path);
    }
    closedir(d);
}

static const char *data_dir(void) {
    static char dir[200];
    static int ready = 0;
    if (!ready) {
        const char *home = getenv("HOME");
        snprintf(dir, sizeof(dir), "%s/.local/share/g510-lcd", home ? home : "/tmp");
        mkdir_p(dir);

        char old_screens[256], new_screens[256];
        snprintf(old_screens, sizeof(old_screens), "%s/custom_screens.txt", PROJECT_DIR);
        snprintf(new_screens, sizeof(new_screens), "%s/custom_screens.txt", dir);
        migrate_file_if_needed(old_screens, new_screens);

        char old_images[256], new_images[256];
        snprintf(old_images, sizeof(old_images), "%s/custom_screen_images", PROJECT_DIR);
        snprintf(new_images, sizeof(new_images), "%s/custom_screen_images", dir);
        migrate_dir_if_needed(old_images, new_images);

        ready = 1;
    }
    return dir;
}

static const char *custom_screens_path(void) {
    static char path[256];
    snprintf(path, sizeof(path), "%s/custom_screens.txt", data_dir());
    return path;
}

/* A drive labeled "frigider", auto-mounted by udisks2 at the standard
   /run/media/$USER/<label> convention -- inherently tied to one
   person's own storage setup, not something a generic sensor name can
   avoid. Built at runtime from $USER rather than baked in at compile
   time (same reasoning as button_log_path() in g510_lcd_buttons.c), so
   this file doesn't hardcode a username. On a machine without this
   exact drive, get_disk_percent() already handles the path not
   existing by showing "N/A" rather than crashing. */
static const char *disk_frigider_path(void) {
    static char path[256];
    const char *user = getenv("USER");
    snprintf(path, sizeof(path), "/run/media/%s/frigider", user ? user : "nobody");
    return path;
}

static void draw_row(g15canvas *c, int y, const char *label, int pct,
                      const char *pct_str, const char *amount, int pct_y_nudge) {
    g15r_G15FontRenderString(c, label_font, (char*)label, 0, LABEL_X, y + LABEL_Y_OFFSET, G15_COLOR_BLACK, 0);
    g15r_renderString(c, (unsigned char*)pct_str, 0, G15_TEXT_SMALL, PCT_X, y + pct_y_nudge);
    draw_slim_bar(c, BAR_X1, BAR_X2, y, BAR_H, pct);
    if (amount) {
        g15r_renderString(c, (unsigned char*)amount, 0, G15_TEXT_SMALL, AMT_X, y);
    }
}

static const char *screen_state_path(void) {
    static char path[256];
    const char *runtime = getenv("XDG_RUNTIME_DIR");
    snprintf(path, sizeof(path), "%s/g510lcd_screen", runtime ? runtime : "/tmp");
    return path;
}

static int read_screen(void) {
    FILE *f = fopen(screen_state_path(), "r");
    if (!f) return 0;
    int s = 0;
    fscanf(f, "%d", &s);
    fclose(f);
    return s;
}

/* Screen 0: the original built-in stats screen. Pulled into its own
   function (was inline in main()) so --preview can render it through the
   exact same code path as the live loop. */
static int max_temp_seen = 0; /* highest temp observed since this program started */

static void draw_stats_screen(g15canvas *canvas) {
    double cpu_pct = get_cpu_percent();
    char cpu_str[16], cpu_ghz_str[16];
    snprintf(cpu_str, sizeof(cpu_str), "%3d%%", (int)(cpu_pct + 0.5));
    snprintf(cpu_ghz_str, sizeof(cpu_ghz_str), "%.1fGHz", get_cpu_ghz());
    draw_row(canvas, ROW_CPU, "CPU", (int)cpu_pct, cpu_str, cpu_ghz_str, 0);

    long ram_used_kb, ram_total_kb;
    get_ram_kb(&ram_used_kb, &ram_total_kb);
    int ram_pct = ram_total_kb > 0 ? (int)(100.0 * ram_used_kb / ram_total_kb) : 0;
    char ram_pct_str[16], ram_amt_str[16];
    snprintf(ram_pct_str, sizeof(ram_pct_str), "%3d%%", ram_pct);
    snprintf(ram_amt_str, sizeof(ram_amt_str), "%.1fG", ram_used_kb / (1024.0 * 1024.0));
    draw_row(canvas, ROW_RAM, "RAM", ram_pct, ram_pct_str, ram_amt_str, 0);

    unsigned long long vram_used, vram_total;
    get_vram_bytes(&vram_used, &vram_total);
    int vram_pct = vram_total > 0 ? (int)(100.0 * vram_used / vram_total) : 0;
    char vram_pct_str[16], vram_amt_str[16];
    snprintf(vram_pct_str, sizeof(vram_pct_str), "%3d%%", vram_pct);
    format_gb(vram_used, vram_amt_str, sizeof(vram_amt_str));
    draw_row(canvas, ROW_VRAM, "VRAM", vram_pct, vram_pct_str, vram_amt_str, 0);

    int temp_c = get_cpu_temp_c();
    if (temp_c > max_temp_seen) max_temp_seen = temp_c;
    char temp_str[16], temp_max_str[16];
    snprintf(temp_str, sizeof(temp_str), "%d" "\xB0" "C", temp_c);
    snprintf(temp_max_str, sizeof(temp_max_str), "MAX %d" "\xB0" "C", max_temp_seen);
    /* temp bar: use % of a 0-90C scale just to give a visual sense of magnitude */
    int temp_pct = temp_c > 0 ? (temp_c * 100 / 90) : 0;
    draw_row(canvas, ROW_TEMP, "TEMP", temp_pct, temp_str, temp_max_str, 1);
}

/* Screen 1: a simple large clock. New screens go here -- L1 cycles
   through however many screens NUM_SCREENS (in g510_lcd_buttons.c)
   currently accounts for. */
static void draw_clock_screen(g15canvas *c) {
    time_t now = time(NULL);
    struct tm *t = localtime(&now);
    char time_str[16], date_str[32];
    strftime(time_str, sizeof(time_str), "%H:%M:%S", t);
    strftime(date_str, sizeof(date_str), "%A, %d %B", t);

    g15r_G15FPrint(c, time_str, 20, 8, G15_TEXT_LARGE, G15_JUSTIFY_LEFT, G15_COLOR_BLACK, 0);
    g15r_renderString(c, (unsigned char*)date_str, 0, G15_TEXT_SMALL, 10, 30);
}

/* --- Custom Screens (v1.1): user-built dashboards for L2-L5 --- */

typedef struct {
    const char *key;    /* used in custom_screens.txt and the GUI dropdown */
    const char *label;  /* short on-screen label (fits the tiny font) */
    int is_percent;      /* naturally 0-100 -- bar-capable, no scale guessing */
    int is_temp;          /* temperature in C -- bar-capable via the existing 0-90C convention */
} sensor_def_t;

static const sensor_def_t SENSORS[] = {
    {"CPU_PCT",          "CPU",  1, 0},
    {"CPU_GHZ",          "GHZ",  0, 0},
    {"CPU_TEMP",         "TEMP", 0, 1},
    {"RAM_PCT",          "RAM",  1, 0},
    {"RAM_AMOUNT",       "AMT",  0, 0},
    {"VRAM_PCT",         "VRAM", 1, 0},
    {"VRAM_AMOUNT",      "AMT",  0, 0},
    {"MAXTEMP",          "MAXT", 0, 1},
    {"GPU_PCT",          "GPU",  1, 0},
    {"GPU_EDGE_TEMP",    "EDGE", 0, 1},
    {"GPU_HOTSPOT_TEMP", "HOT",  0, 1},
    {"GPU_VRAM_TEMP",    "VMEM", 0, 1},
    {"SWAP_PCT",         "SWAP", 1, 0},
    {"DISK_ROOT_PCT",    "DISK", 1, 0},
    {"DISK_FRIGIDER_PCT","FRIG", 1, 0},
    {"UPTIME",           "UPTM", 0, 0},
    {"NET_DOWN",         "DOWN", 0, 0},
    {"NET_UP",           "UPLD", 0, 0},
    {"TIME",             "TIME", 0, 0},
    {"DATE",             "DATE", 0, 0},
    {"MB_TEMP1",         "MB1",  0, 1},
    {"MB_TEMP2",         "MB2",  0, 1},
    {"MB_TEMP3",         "MB3",  0, 1},
    {"MB_TEMP4",         "MB4",  0, 1},
    {"MB_TEMP5",         "MB5",  0, 1},
    {"MB_TEMP6",         "MB6",  0, 1},
};

static const sensor_def_t *find_sensor(const char *key) {
    for (size_t i = 0; i < sizeof(SENSORS) / sizeof(SENSORS[0]); i++)
        if (strcmp(SENSORS[i].key, key) == 0) return &SENSORS[i];
    return NULL;
}

/* Fills pct_for_bar (0-100, or -1 if this sensor has no honest bar scale /
   is currently unavailable) and a short display string for the value. */
static void get_sensor_value(const char *key, double *pct_for_bar, char *disp, size_t displen) {
    *pct_for_bar = -1;
    disp[0] = 0;

    if (strcmp(key, "CPU_PCT") == 0) {
        double v = get_cpu_percent();
        *pct_for_bar = v;
        snprintf(disp, displen, "%d%%", (int)(v + 0.5));
    } else if (strcmp(key, "CPU_GHZ") == 0) {
        snprintf(disp, displen, "%.1fGHz", get_cpu_ghz());
    } else if (strcmp(key, "CPU_TEMP") == 0) {
        int t = get_cpu_temp_c();
        *pct_for_bar = t > 0 ? t * 100.0 / 90.0 : 0;
        snprintf(disp, displen, "%d\xB0" "C", t);
    } else if (strcmp(key, "RAM_PCT") == 0) {
        long u, t; get_ram_kb(&u, &t);
        double v = t > 0 ? 100.0 * u / t : 0;
        *pct_for_bar = v;
        snprintf(disp, displen, "%d%%", (int)(v + 0.5));
    } else if (strcmp(key, "RAM_AMOUNT") == 0) {
        long u, t; get_ram_kb(&u, &t);
        snprintf(disp, displen, "%.1fG", u / (1024.0 * 1024.0));
    } else if (strcmp(key, "VRAM_PCT") == 0) {
        unsigned long long u, t; get_vram_bytes(&u, &t);
        double v = t > 0 ? 100.0 * u / t : 0;
        *pct_for_bar = v;
        snprintf(disp, displen, "%d%%", (int)(v + 0.5));
    } else if (strcmp(key, "VRAM_AMOUNT") == 0) {
        unsigned long long u, t; get_vram_bytes(&u, &t);
        format_gb(u, disp, displen);
    } else if (strcmp(key, "MAXTEMP") == 0) {
        snprintf(disp, displen, "%d\xB0" "C", max_temp_seen);
    } else if (strcmp(key, "GPU_PCT") == 0) {
        double v = get_gpu_percent();
        if (v < 0) snprintf(disp, displen, "N/A");
        else { *pct_for_bar = v; snprintf(disp, displen, "%d%%", (int)v); }
    } else if (strcmp(key, "GPU_EDGE_TEMP") == 0) {
        int t = read_hwmon_temp_c("/sys/class/hwmon/hwmon2/temp1_input");
        *pct_for_bar = t > 0 ? t * 100.0 / 90.0 : 0;
        snprintf(disp, displen, "%d\xB0" "C", t);
    } else if (strcmp(key, "GPU_HOTSPOT_TEMP") == 0) {
        int t = read_hwmon_temp_c("/sys/class/hwmon/hwmon2/temp2_input");
        *pct_for_bar = t > 0 ? t * 100.0 / 90.0 : 0;
        snprintf(disp, displen, "%d\xB0" "C", t);
    } else if (strcmp(key, "GPU_VRAM_TEMP") == 0) {
        int t = read_hwmon_temp_c("/sys/class/hwmon/hwmon2/temp3_input");
        *pct_for_bar = t > 0 ? t * 100.0 / 90.0 : 0;
        snprintf(disp, displen, "%d\xB0" "C", t);
    } else if (strcmp(key, "SWAP_PCT") == 0) {
        double v = get_swap_percent();
        *pct_for_bar = v;
        snprintf(disp, displen, "%d%%", (int)(v + 0.5));
    } else if (strcmp(key, "DISK_ROOT_PCT") == 0) {
        double v = get_disk_percent("/");
        if (v < 0) snprintf(disp, displen, "N/A");
        else { *pct_for_bar = v; snprintf(disp, displen, "%d%%", (int)(v + 0.5)); }
    } else if (strcmp(key, "DISK_FRIGIDER_PCT") == 0) {
        double v = get_disk_percent(disk_frigider_path());
        if (v < 0) snprintf(disp, displen, "N/A");
        else { *pct_for_bar = v; snprintf(disp, displen, "%d%%", (int)(v + 0.5)); }
    } else if (strcmp(key, "UPTIME") == 0) {
        snprintf(disp, displen, "%.0fh", get_uptime_hours());
    } else if (strcmp(key, "NET_DOWN") == 0) {
        format_kbps(g_net_down_kbps, disp, displen);
    } else if (strcmp(key, "NET_UP") == 0) {
        format_kbps(g_net_up_kbps, disp, displen);
    } else if (strcmp(key, "TIME") == 0) {
        time_t now = time(NULL);
        strftime(disp, displen, "%H:%M:%S", localtime(&now));
    } else if (strcmp(key, "DATE") == 0) {
        time_t now = time(NULL);
        strftime(disp, displen, "%d %b", localtime(&now));
    } else if (strncmp(key, "MB_TEMP", 7) == 0) {
        int n = atoi(key + 7);
        char path[128];
        snprintf(path, sizeof(path), "/sys/class/hwmon/hwmon4/temp%d_input", n);
        int t = read_hwmon_temp_c(path);
        *pct_for_bar = t > 0 ? t * 100.0 / 90.0 : 0;
        snprintf(disp, displen, "%d\xB0" "C", t);
    }
}

#define MAX_ELEMENTS 8
#define MAX_IMAGES 2 /* the screen is 160x43 -- rarely useful to fit more than this */
#define MAX_CUSTOM_SCREENS 4 /* L2, L3, L4, L5 */

typedef struct {
    char sensor[24];
    char style[8]; /* "number" or "bar" */
    int x, y;
    int width; /* bar length in px, only meaningful for style="bar" -- ignored for "number" */
} element_t;

/* A converted-to-1bpp image placed on a custom screen -- see
   src/png-to-lcd.py (the conversion step) and draw_image_element()
   below (the render step, reusing g15r_drawXBM(), both already
   verified working independently and together before this was wired
   in). No resize in this first version -- width/height are fixed at
   import time by png-to-lcd.py's max_width parameter and the source
   image's own aspect ratio; only position (x, y) is editable, via the
   same drag mechanic as sensor elements. */
typedef struct {
    char path[128]; /* relative to data_dir(), e.g. "custom_screen_images/logo.bin" */
    int x, y, width, height;
} image_t;

typedef struct {
    element_t elements[MAX_ELEMENTS];
    int count;
    image_t images[MAX_IMAGES];
    int image_count;
} custom_screen_t;

static custom_screen_t custom_screens[MAX_CUSTOM_SCREENS];

/* Reloaded every time a custom screen is drawn (cheap, small file) so
   edits made live in the GUI show up on the next frame without needing
   the daemon restarted. */
static void load_custom_screens(void) {
    for (int i = 0; i < MAX_CUSTOM_SCREENS; i++) {
        custom_screens[i].count = 0;
        custom_screens[i].image_count = 0;
    }
    FILE *f = fopen(custom_screens_path(), "r");
    if (!f) return;
    char line[256];
    int current = -1;
    while (fgets(line, sizeof(line), f)) {
        char *nl = strchr(line, '\n');
        if (nl) *nl = 0;
        if (strncmp(line, "SCREEN L", 8) == 0) {
            int n = atoi(line + 8);
            current = (n >= 2 && n <= 5) ? n - 2 : -1;
        } else if (strncmp(line, "ELEMENT ", 8) == 0 && current >= 0) {
            custom_screen_t *cs = &custom_screens[current];
            if (cs->count >= MAX_ELEMENTS) continue;
            element_t *el = &cs->elements[cs->count];
            el->sensor[0] = 0; el->style[0] = 0; el->x = 0; el->y = 0;
            el->width = 40; /* matches the previous hardcoded bar length -- old
                                config lines with no width= keep looking identical */
            char rest[256];
            strncpy(rest, line + 8, sizeof(rest) - 1);
            rest[sizeof(rest) - 1] = 0;
            char *tok = strtok(rest, " ");
            while (tok) {
                char key[32], val[64];
                if (sscanf(tok, "%31[^=]=%63s", key, val) == 2) {
                    if (strcmp(key, "sensor") == 0) { strncpy(el->sensor, val, sizeof(el->sensor) - 1); el->sensor[sizeof(el->sensor) - 1] = 0; }
                    else if (strcmp(key, "style") == 0) { strncpy(el->style, val, sizeof(el->style) - 1); el->style[sizeof(el->style) - 1] = 0; }
                    else if (strcmp(key, "x") == 0) el->x = atoi(val);
                    else if (strcmp(key, "y") == 0) el->y = atoi(val);
                    else if (strcmp(key, "width") == 0) el->width = atoi(val);
                }
                tok = strtok(NULL, " ");
            }
            if (el->sensor[0]) cs->count++;
        } else if (strncmp(line, "IMAGE ", 6) == 0 && current >= 0) {
            custom_screen_t *cs = &custom_screens[current];
            if (cs->image_count >= MAX_IMAGES) continue;
            image_t *im = &cs->images[cs->image_count];
            im->path[0] = 0; im->x = 0; im->y = 0; im->width = 0; im->height = 0;
            char rest[256];
            strncpy(rest, line + 6, sizeof(rest) - 1);
            rest[sizeof(rest) - 1] = 0;
            char *tok = strtok(rest, " ");
            while (tok) {
                char key[32], val[192];
                if (sscanf(tok, "%31[^=]=%191s", key, val) == 2) {
                    if (strcmp(key, "path") == 0) { strncpy(im->path, val, sizeof(im->path) - 1); im->path[sizeof(im->path) - 1] = 0; }
                    else if (strcmp(key, "x") == 0) im->x = atoi(val);
                    else if (strcmp(key, "y") == 0) im->y = atoi(val);
                    else if (strcmp(key, "width") == 0) im->width = atoi(val);
                    else if (strcmp(key, "height") == 0) im->height = atoi(val);
                }
                tok = strtok(NULL, " ");
            }
            /* clamp to screen bounds -- guards against a hand-edited config
               (this format is deliberately hand-editable) requesting a
               malloc/fread far larger than the 160x43 screen could ever need */
            if (im->path[0] && im->width > 0 && im->width <= G15_LCD_WIDTH &&
                im->height > 0 && im->height <= G15_LCD_HEIGHT) cs->image_count++;
        }
    }
    fclose(f);
}

/* Real rendered bounds per element, recorded every time draw_element()
   runs -- so the GUI editor can position drag/resize hit-boxes exactly
   where things actually are instead of guessing. Python has no way to
   compute label_w itself (that needs the label font's real glyph
   metrics), which is exactly what made the old fixed-offset resize
   handle drift away from the real bar -- "hard to control", reported
   directly. Emitted as a sidecar file only in --preview mode (see
   main()); the live LCD-writing path never touches this, zero cost
   there. */
typedef struct {
    int label_x1, label_y1, label_x2, label_y2; /* covers just the label glyph */
    int is_bar;
    int bar_x1, bar_x2, bar_y1, bar_y2;           /* only valid if is_bar */
} element_bounds_t;

static element_bounds_t g_element_bounds[MAX_ELEMENTS];
static int g_element_bounds_count = 0;

static void draw_element(g15canvas *c, element_t *el) {
    const sensor_def_t *def = find_sensor(el->sensor);
    if (!def) return;
    double pct_for_bar;
    char disp[32];
    get_sensor_value(el->sensor, &pct_for_bar, disp, sizeof(disp));

    g15r_G15FontRenderString(c, label_font, (char*)def->label, 0, el->x, el->y + LABEL_Y_OFFSET, G15_COLOR_BLACK, 0);
    int label_w = g15r_testG15FontWidth(label_font, (char*)def->label);
    int value_x = el->x + label_w + 4;

    element_bounds_t *b = (g_element_bounds_count < MAX_ELEMENTS)
        ? &g_element_bounds[g_element_bounds_count++] : NULL;
    if (b) {
        b->label_x1 = el->x; b->label_y1 = el->y;
        b->label_x2 = el->x + label_w; b->label_y2 = el->y + label_font->font_height;
        b->is_bar = 0;
    }

    /* "bar" only ever applies to a sensor with an honest 0-100 scale
       (a true percent, or a temperature via the same 0-90C convention
       already used on the built-in stats screen). Anything else silently
       falls back to number style rather than inventing a scale. */
    if (strcmp(el->style, "bar") == 0 && (def->is_percent || def->is_temp) && pct_for_bar >= 0) {
        int bar_x1 = value_x;
        int bar_x2 = bar_x1 + el->width;
        draw_slim_bar(c, bar_x1, bar_x2, el->y, BAR_H, (int)pct_for_bar);
        g15r_renderString(c, (unsigned char*)disp, 0, G15_TEXT_SMALL, bar_x2 + 4, el->y);
        if (b) {
            b->is_bar = 1;
            b->bar_x1 = bar_x1; b->bar_x2 = bar_x2;
            b->bar_y1 = el->y; b->bar_y2 = el->y + BAR_H;
        }
    } else {
        g15r_renderString(c, (unsigned char*)disp, 0, G15_TEXT_SMALL, value_x, el->y);
    }
}

/* Writes the bounds sidecar for --preview mode. Plain text, one line
   per element in the same order load_custom_screens() produced them
   (matches the GUI's own element list index-for-index). */
static void write_bounds_meta(const char *outpath) {
    char meta_path[300];
    snprintf(meta_path, sizeof(meta_path), "%s.meta", outpath);
    FILE *f = fopen(meta_path, "w");
    if (!f) return;
    for (int i = 0; i < g_element_bounds_count; i++) {
        element_bounds_t *b = &g_element_bounds[i];
        if (b->is_bar) {
            fprintf(f, "%d label_x1=%d label_y1=%d label_x2=%d label_y2=%d bar_x1=%d bar_y1=%d bar_x2=%d bar_y2=%d\n",
                    i, b->label_x1, b->label_y1, b->label_x2, b->label_y2,
                    b->bar_x1, b->bar_y1, b->bar_x2, b->bar_y2);
        } else {
            fprintf(f, "%d label_x1=%d label_y1=%d label_x2=%d label_y2=%d\n",
                    i, b->label_x1, b->label_y1, b->label_x2, b->label_y2);
        }
    }
    fclose(f);
}

/* Loads a converted 1bpp image (see src/png-to-lcd.py) and draws it via
   g15r_drawXBM() -- same function, same call shape, already verified
   working end to end (both the conversion step and this render step)
   before this was wired into the real custom-screen system. Silently
   does nothing if the file can't be read (e.g. it was deleted by hand)
   rather than crashing the whole screen over one missing image. */
static void draw_image_element(g15canvas *c, image_t *im) {
    char full_path[300];
    snprintf(full_path, sizeof(full_path), "%s/%s", data_dir(), im->path);
    FILE *f = fopen(full_path, "rb");
    if (!f) return;
    long expected = (long)((im->width + 7) / 8) * im->height;
    unsigned char *data = malloc(expected);
    if (!data) { fclose(f); return; }
    size_t got = fread(data, 1, expected, f);
    fclose(f);
    if ((long)got == expected) {
        g15r_drawXBM(c, data, im->width, im->height, im->x, im->y);
    }
    free(data);
}

static void draw_custom_screen(g15canvas *c, int screen_num) {
    g_element_bounds_count = 0;
    load_custom_screens();
    custom_screen_t *cs = &custom_screens[screen_num - 2];
    if (cs->count == 0 && cs->image_count == 0) {
        char label[8];
        snprintf(label, sizeof(label), "L%d", screen_num);
        g15r_G15FPrint(c, label, 0, 8, G15_TEXT_LARGE, G15_JUSTIFY_CENTER, G15_COLOR_BLACK, 0);
        g15r_renderString(c, (unsigned char*)"not set up yet", 0, G15_TEXT_SMALL, 24, 30);
        return;
    }
    for (int i = 0; i < cs->count; i++) draw_element(c, &cs->elements[i]);
    for (int i = 0; i < cs->image_count; i++) draw_image_element(c, &cs->images[i]);
}

int main(int argc, char **argv) {
    label_font = g15r_loadG15Font(FONT_PATH);
    if (!label_font) { fprintf(stderr, "failed to load custom font\n"); return 1; }

    /* One-shot preview mode: render a single screen to an image file
       through the exact same drawing code as the live LCD, then exit.
       Used by the GUI's live editor -- never touches /dev/g510-lcd. */
    if (argc >= 3 && strcmp(argv[1], "--preview") == 0) {
        int screen = atoi(argv[2]);
        const char *outpath = argc >= 4 ? argv[3] : "/tmp/g510_preview.ppm";
        g15canvas canvas;
        g15r_initCanvas(&canvas);
        update_net_speed();
        if (screen == 1) draw_clock_screen(&canvas);
        else if (screen >= 2 && screen <= 5) {
            draw_custom_screen(&canvas, screen);
            write_bounds_meta(outpath);
        } else draw_stats_screen(&canvas);
        write_ppm(&canvas, outpath);
        return 0;
    }

    while (1) {
        g15canvas canvas;
        g15r_initCanvas(&canvas);
        update_net_speed();

        int screen = read_screen();
        if (screen == 1) {
            draw_clock_screen(&canvas);
            send_frame(&canvas);
            sleep(1);
            continue;
        }
        if (screen >= 2 && screen <= 5) {
            draw_custom_screen(&canvas, screen);
            send_frame(&canvas);
            sleep(1);
            continue;
        }

        draw_stats_screen(&canvas);
        send_frame(&canvas);
        sleep(2);
    }
    return 0;
}
