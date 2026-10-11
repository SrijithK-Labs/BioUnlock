// Ticket.cpp - reads and validates the machine-DPAPI unlock ticket.

#include "Ticket.h"

#include <cstring>
#include <ctime>

namespace {

constexpr BYTE kMagic[16] = {'B', 'I', 'O', 'U', 'N', 'L', 'O', 'C', 'K',
                             '-', 'T', 'I', 'C', 'K', 'E', 'T'};
constexpr uint32_t kTicketVersion = 1;

std::wstring ProgramDataDir() {
    wchar_t buffer[MAX_PATH] = {};
    DWORD len = GetEnvironmentVariableW(L"ProgramData", buffer, MAX_PATH);
    if (len > 0 && len < MAX_PATH) {
        return std::wstring(buffer, len);
    }
    wchar_t folder[MAX_PATH] = {};
    if (SUCCEEDED(SHGetFolderPathW(nullptr, CSIDL_COMMON_APPDATA, nullptr, 0, folder))) {
        return std::wstring(folder);
    }
    return L"C:\\ProgramData";
}

bool ReadRaw(const std::string& data, size_t& offset, void* out, size_t count) {
    if (offset + count > data.size()) {
        return false;
    }
    memcpy(out, data.data() + offset, count);
    offset += count;
    return true;
}

bool ReadField(const std::string& data, size_t& offset, std::wstring& out) {
    uint16_t length = 0;
    if (!ReadRaw(data, offset, &length, sizeof(length))) {
        return false;
    }
    if (offset + length > data.size()) {
        return false;
    }
    const char* start = data.data() + offset;
    offset += length;
    if (length == 0) {
        out.clear();
        return true;
    }
    int wide = MultiByteToWideChar(CP_UTF8, 0, start, static_cast<int>(length), nullptr, 0);
    if (wide <= 0) {
        return false;
    }
    std::wstring result(static_cast<size_t>(wide), L'\0');
    MultiByteToWideChar(CP_UTF8, 0, start, static_cast<int>(length), result.data(), wide);
    out = std::move(result);
    return true;
}

std::optional<std::string> ReadFileBytes(const std::wstring& path) {
    HANDLE file = CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr, OPEN_EXISTING,
                              FILE_ATTRIBUTE_NORMAL, nullptr);
    if (file == INVALID_HANDLE_VALUE) {
        return std::nullopt;
    }
    LARGE_INTEGER size = {};
    if (!GetFileSizeEx(file, &size) || size.QuadPart <= 0 || size.QuadPart > 64 * 1024) {
        CloseHandle(file);
        return std::nullopt;
    }
    std::string data(static_cast<size_t>(size.QuadPart), '\0');
    DWORD read = 0;
    BOOL ok = ReadFile(file, data.data(), static_cast<DWORD>(data.size()), &read, nullptr);
    CloseHandle(file);
    if (!ok || read != data.size()) {
        return std::nullopt;
    }
    return data;
}

std::optional<std::string> Unprotect(const std::string& blob) {
    if (blob.size() < 4) {
        return std::nullopt;
    }
    DATA_BLOB in = {};
    in.pbData = reinterpret_cast<BYTE*>(const_cast<char*>(blob.data()));
    in.cbData = static_cast<DWORD>(blob.size());
    DATA_BLOB out = {};
    if (!CryptUnprotectData(&in, nullptr, nullptr, nullptr, nullptr, 0, &out)) {
        return std::nullopt;
    }
    std::string result(reinterpret_cast<char*>(out.pbData), out.cbData);
    SecureZeroMemory(out.pbData, out.cbData);
    LocalFree(out.pbData);
    return result;
}

}  // namespace

std::wstring SharedDir() {
    return ProgramDataDir() + L"\\BioUnlock";
}

std::wstring TicketFilePath() {
    return SharedDir() + L"\\" + BIOUNLOCK_TICKET_FILENAME;
}

void ClearUnlockTicket() {
    DeleteFileW(TicketFilePath().c_str());
}

std::optional<TicketData> ReadUnlockTicket() {
    auto blob = ReadFileBytes(TicketFilePath());
    if (!blob) {
        return std::nullopt;
    }
    auto data = Unprotect(*blob);
    if (!data) {
        return std::nullopt;
    }

    const std::string& buffer = *data;
    if (buffer.size() < sizeof(kMagic) + sizeof(uint32_t) + 2 * sizeof(uint64_t)) {
        return std::nullopt;
    }
    if (memcmp(buffer.data(), kMagic, sizeof(kMagic)) != 0) {
        return std::nullopt;
    }

    size_t offset = sizeof(kMagic);
    uint32_t version = 0;
    uint64_t issuedAt = 0;
    uint64_t expiresAt = 0;
    if (!ReadRaw(buffer, offset, &version, sizeof(version))) {
        return std::nullopt;
    }
    if (!ReadRaw(buffer, offset, &issuedAt, sizeof(issuedAt))) {
        return std::nullopt;
    }
    if (!ReadRaw(buffer, offset, &expiresAt, sizeof(expiresAt))) {
        return std::nullopt;
    }
    if (version != kTicketVersion) {
        return std::nullopt;
    }

    TicketData ticket;
    ticket.issuedAt = issuedAt;
    ticket.expiresAt = expiresAt;
    if (!ReadField(buffer, offset, ticket.requestId)) {
        return std::nullopt;
    }
    if (!ReadField(buffer, offset, ticket.username)) {
        return std::nullopt;
    }
    if (!ReadField(buffer, offset, ticket.domain)) {
        return std::nullopt;
    }
    if (!ReadField(buffer, offset, ticket.password)) {
        return std::nullopt;
    }

    const unsigned long long now = static_cast<unsigned long long>(time(nullptr));
    if (ticket.expiresAt <= now) {
        return std::nullopt;
    }
    return ticket;
}
