/* Exact raw received_at contract: ASCII UTC, seconds or six fractional digits.
 * Pure scalar validation: no database access, I/O or mutable row facts.
 * One connection-local positive prefix cache holds only calendar validity.
 * All byte offsets are inspected only after verifying the complete byte length.
 */
#include <sqlite3ext.h>
#include <string.h>
SQLITE_EXTENSION_INIT1

typedef struct { unsigned char prefix[19]; int valid; } CalendarCache;

static int digits(const unsigned char *text, int start, int count) {
    int value = 0;
    for (int i = start; i < start + count; i++) {
        if (text[i] < '0' || text[i] > '9') return -1;
        value = value * 10 + text[i] - '0';
    }
    return value;
}

static void raw_time_valid(sqlite3_context *context, int argc, sqlite3_value **argv) {
    (void)argc;
    if (sqlite3_value_type(argv[0]) != SQLITE_TEXT) {
        sqlite3_result_int(context, 0);
        return;
    }
    const unsigned char *text = sqlite3_value_text(argv[0]);
    if (!text) {
        sqlite3_result_error_nomem(context);
        return;
    }
    int length = sqlite3_value_bytes(argv[0]);
    if (length != 25 && length != 32) goto invalid;
    int zone = length == 25 ? 19 : 26;
    if (length == 32 && (text[19] != '.' || digits(text, 20, 6) < 0)) goto invalid;
    if (text[zone] != '+' || text[zone + 1] != '0' || text[zone + 2] != '0' ||
        text[zone + 3] != ':' || text[zone + 4] != '0' || text[zone + 5] != '0') goto invalid;
    CalendarCache *cache = sqlite3_user_data(context);
    /* Exact prefix bytes are a pure validity fact, not row membership. Complete
     * length/fraction/UTC suffix checks above run even on every cache hit. */
    if (cache->valid && memcmp(cache->prefix, text, 19) == 0) {
        sqlite3_result_int(context, 1);
        return;
    }
    if (text[4] != '-' || text[7] != '-' || text[10] != 'T' ||
        text[13] != ':' || text[16] != ':') goto invalid;
    int year = digits(text, 0, 4), month = digits(text, 5, 2), day = digits(text, 8, 2);
    int hour = digits(text, 11, 2), minute = digits(text, 14, 2), second = digits(text, 17, 2);
    if (year < 1 || month < 1 || month > 12 || day < 1 ||
        hour < 0 || hour > 23 || minute < 0 || minute > 59 || second < 0 || second > 59) goto invalid;
    static const int days[] = {0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
    int leap = year % 4 == 0 && (year % 100 != 0 || year % 400 == 0);
    if (day > days[month] + (month == 2 && leap)) goto invalid;
    memcpy(cache->prefix, text, 19);
    cache->valid = 1;
    sqlite3_result_int(context, 1);
    return;
invalid:
    sqlite3_result_int(context, 0);
}

#ifdef _WIN32
__declspec(dllexport)
#endif
int sqlite3_extension_init(sqlite3 *db, char **error, const sqlite3_api_routines *api) {
    (void)error;
    SQLITE_EXTENSION_INIT2(api);
    CalendarCache *cache = sqlite3_malloc(sizeof(CalendarCache));
    if (!cache) return SQLITE_NOMEM;
    cache->valid = 0;
    return sqlite3_create_function_v2(db, "retention_raw_time_valid_v1", 1,
        SQLITE_UTF8 | SQLITE_DETERMINISTIC | SQLITE_DIRECTONLY,
        cache, raw_time_valid, 0, 0, sqlite3_free);
}
