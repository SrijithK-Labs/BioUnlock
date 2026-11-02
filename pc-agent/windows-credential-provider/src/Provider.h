// Provider.h - credential provider and credential interfaces.
#pragma once

#include "Common.h"
#include "Ticket.h"

enum BIOUNLOCK_FIELD_ID {
    FI_TILEIMAGE = 0,
    FI_LABEL,
    FI_SUBMIT_BUTTON,
    FI_NUM_FIELDS,
};

// State shared between the provider and the credentials it hands out.
struct ProviderState {
    std::mutex mutex;
    std::optional<TicketData> ticket;
    std::atomic<bool> stopping{false};

    std::optional<TicketData> Snapshot() {
        std::lock_guard<std::mutex> lock(mutex);
        return ticket;
    }
};

class CBioUnlockProvider : public ICredentialProvider, public ICredentialProviderSetUserArray {
  public:
    CBioUnlockProvider();

    // IUnknown
    IFACEMETHODIMP QueryInterface(REFIID riid, void** ppv) override;
    IFACEMETHODIMP_(ULONG) AddRef() override;
    IFACEMETHODIMP_(ULONG) Release() override;

    // ICredentialProvider
    IFACEMETHODIMP SetUsageScenario(CREDENTIAL_PROVIDER_USAGE_SCENARIO cpus, DWORD dwFlags) override;
    IFACEMETHODIMP SetSerialization(const CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION* pcpcs) override;
    IFACEMETHODIMP Advise(ICredentialProviderEvents* pcpe, UINT_PTR upAdviseContext) override;
    IFACEMETHODIMP UnAdvise() override;
    IFACEMETHODIMP GetFieldDescriptorCount(DWORD* pdwCount) override;
    IFACEMETHODIMP GetFieldDescriptorAt(DWORD dwIndex,
                                        CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR** ppcpfd) override;
    IFACEMETHODIMP GetCredentialCount(DWORD* pdwCount, DWORD* pdwDefault,
                                      BOOL* pbAutoLogonWithDefault) override;
    IFACEMETHODIMP GetCredentialAt(DWORD dwIndex, ICredentialProviderCredential** ppcpc) override;

    // ICredentialProviderSetUserArray
    IFACEMETHODIMP SetUserArray(ICredentialProviderUserArray* users) override;

  private:
    ~CBioUnlockProvider();
    void StartWatcher();
    void StopWatcher();
    void WatcherLoop();
    std::optional<TicketData> RefreshTicket();

    LONG _cRef;
    CREDENTIAL_PROVIDER_USAGE_SCENARIO _cpus;
    ICredentialProviderEvents* _pEvents;
    UINT_PTR _upAdviseContext;
    std::shared_ptr<ProviderState> _state;
    std::thread _watcher;
};

class CBioUnlockCredential : public ICredentialProviderCredential {
  public:
    CBioUnlockCredential(std::shared_ptr<ProviderState> state,
                         CREDENTIAL_PROVIDER_USAGE_SCENARIO cpus);

    // IUnknown
    IFACEMETHODIMP QueryInterface(REFIID riid, void** ppv) override;
    IFACEMETHODIMP_(ULONG) AddRef() override;
    IFACEMETHODIMP_(ULONG) Release() override;

    // ICredentialProviderCredential
    IFACEMETHODIMP Advise(ICredentialProviderCredentialEvents* pcpce) override;
    IFACEMETHODIMP UnAdvise() override;
    IFACEMETHODIMP SetSelected(BOOL* pbAutoLogon) override;
    IFACEMETHODIMP SetDeselected() override;
    IFACEMETHODIMP GetFieldState(DWORD dwFieldID, CREDENTIAL_PROVIDER_FIELD_STATE* pcpfs,
                                 CREDENTIAL_PROVIDER_FIELD_INTERACTIVE_STATE* pcpfis) override;
    IFACEMETHODIMP GetStringValue(DWORD dwFieldID, PWSTR* ppwsz) override;
    IFACEMETHODIMP GetBitmapValue(DWORD dwFieldID, HBITMAP* phbmp) override;
    IFACEMETHODIMP GetCheckboxValue(DWORD dwFieldID, BOOL* pbChecked, PWSTR* ppwszLabel) override;
    IFACEMETHODIMP GetSubmitButtonValue(DWORD dwFieldID, DWORD* pdwAdjacentTo) override;
    IFACEMETHODIMP GetComboBoxValueCount(DWORD dwFieldID, DWORD* pcItems,
                                         DWORD* pdwSelectedItem) override;
    IFACEMETHODIMP GetComboBoxValueAt(DWORD dwFieldID, DWORD dwItem, PWSTR* ppwszItem) override;
    IFACEMETHODIMP SetStringValue(DWORD dwFieldID, PCWSTR pcwsz) override;
    IFACEMETHODIMP SetCheckboxValue(DWORD dwFieldID, BOOL bChecked) override;
    IFACEMETHODIMP SetComboBoxSelectedValue(DWORD dwFieldID, DWORD dwSelectedItem) override;
    IFACEMETHODIMP CommandLinkClicked(DWORD dwFieldID) override;
    IFACEMETHODIMP GetSerialization(CREDENTIAL_PROVIDER_GET_SERIALIZATION_RESPONSE* pcpgsr,
                                    CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION* pcpcs,
                                    PWSTR* ppwszOptionalStatusText,
                                    CREDENTIAL_PROVIDER_STATUS_ICON* pcpsiOptionalStatusIcon) override;
    IFACEMETHODIMP ReportResult(NTSTATUS ntsStatus, NTSTATUS ntsSubstatus,
                                PWSTR* ppwszOptionalStatusText,
                                CREDENTIAL_PROVIDER_STATUS_ICON* pcpsiOptionalStatusIcon) override;

  private:
    ~CBioUnlockCredential();

    LONG _cRef;
    std::shared_ptr<ProviderState> _state;
    CREDENTIAL_PROVIDER_USAGE_SCENARIO _cpus;
    ICredentialProviderCredentialEvents* _pEvents;
};
