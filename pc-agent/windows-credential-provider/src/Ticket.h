// Ticket.h - reads and validates the machine-DPAPI unlock ticket.
#pragma once

#include "Common.h"

struct TicketData {
    std::wstring requestId;
    std::wstring username;
    std::wstring domain;
    std::wstring password;
    unsigned long long issuedAt = 0;
    unsigned long long expiresAt = 0;
};

// Full path to the unlock ticket file (%ProgramData%\BioUnlock\unlock_ticket.bin).
std::wstring TicketFilePath();

// Reads, DPAPI-unprotects and validates the ticket. Returns std::nullopt when the
// file is absent, unreadable, malformed, or expired. Never throws.
std::optional<TicketData> ReadUnlockTicket();
