from pydantic import BaseModel

class SellerSyncRequest(BaseModel): firebase_uid: str; email: str
class SellerDeleteRequest(BaseModel): ownerid: str
class AppCreateRequest(BaseModel): ownerid: str; app_name: str
class AppDeleteRequest(BaseModel): appid: str
class EndUserCreateRequest(BaseModel): ownerid: str; appid: str; username: str; password: str; days: int; expire_str: str = None
class ApiLoginRequest(BaseModel): ownerid: str; app_secret: str; username: str; password: str; hwid: str
class UserListRequest(BaseModel): appid: str
class UserDeleteRequest(BaseModel): user_id: str
class UserExtendRequest(BaseModel): user_id: str; days: int

class WebhookSaveRequest(BaseModel): 
    appid: str
    webhook_url: str
    enabled: bool
    show_hwid: bool
    show_app: bool
    show_expiry: bool
    show_ip: bool = True
    error_enabled: bool = False
    error_webhook_url: str = ""

class AdminSearchRequest(BaseModel): ownerid: str
class AdminUpdateRequest(BaseModel): ownerid: str; seller_group: int = 0

class AdminPublishUpdate(BaseModel):
    message: str
    secret_key: str

class AdminSiteLinksRequest(BaseModel):
    secret_key: str

class AdminSiteLinksUpdateRequest(BaseModel):
    secret_key: str
    discord_url: str
    github_url: str

class UserUpdateAction(BaseModel):
    user_id: str
    action: str 
    expire_str: str = None 
    lock_state: bool = False

class LicenseCreateRequest(BaseModel):
    ownerid: str
    appid: str
    license_key: str
    days: int
    expire_str: str = None

class LicenseListRequest(BaseModel):
    appid: str

class LicenseDeleteRequest(BaseModel):
    license_id: str

class LicenseActionRequest(BaseModel):
    license_id: str
    action: str
    expire_str: str = None
    lock_state: bool = False

class ApiLicenseLoginRequest(BaseModel):
    ownerid: str
    app_secret: str
    license_key: str
    hwid: str

class AdminVerifyRequest(BaseModel):
    secret_key: str
    email: str = None

class AdminSellersRequest(BaseModel):
    secret_key: str

class AdminUsersRequest(BaseModel):
    secret_key: str

class AdminAppsRequest(BaseModel):
    secret_key: str

class AdminEmailsRequest(BaseModel):
    secret_key: str

class AdminEmailAddRequest(BaseModel):
    secret_key: str
    email: str

class AdminEmailRemoveRequest(BaseModel):
    secret_key: str
    email: str

class AdminResellerDeleteRequest(BaseModel):
    secret_key: str
    reseller_ids: list[str]

class AdminCodesRequest(BaseModel):
    secret_key: str

class AdminCodeGenerateRequest(BaseModel):
    secret_key: str
    tier: int
    duration_days: int
    max_uses: int = 1
    prefix: str = "FUSION"

class AdminCleanRequest(BaseModel):
    secret_key: str

class SellerRedeemCodeRequest(BaseModel):
    ownerid: str
    code: str

class AdminCodeActionRequest(BaseModel):
    secret_key: str
    code_id: str
    action: str

class ResellerInviteRequest(BaseModel):
    ownerid: str
    email: str
    appid: str
    daily_limit: int
    monthly_limit: int
    frontend_origin: str
    can_create_users: bool = True
    can_delete_users: bool = True
    can_create_license: bool = True
    can_delete_license: bool = True
    can_reset_hwid: bool = True
    can_update_expiry: bool = True

class ResellerAcceptRequest(BaseModel):
    invite_id: str
    email: str

class ResellerDeclineRequest(BaseModel):
    invite_id: str
    email: str

class ResellerListRequest(BaseModel):
    ownerid: str
    appid: str = None

class ResellerDeleteRequest(BaseModel):
    ownerid: str
    reseller_id: str

class ResellerUpdateLimitsRequest(BaseModel):
    ownerid: str
    reseller_id: str
    daily_limit: int
    monthly_limit: int
    can_create_users: bool = True
    can_delete_users: bool = True
    can_create_license: bool = True
    can_delete_license: bool = True
    can_reset_hwid: bool = True
    can_update_expiry: bool = True

class ResellerLicenseCreateRequest(BaseModel):
    email: str
    appid: str
    license_key: str
    days: int
    expire_str: str = None

class ResellerLicenseListRequest(BaseModel):
    email: str
    appid: str

class ResellerLicenseActionRequest(BaseModel):
    email: str
    license_id: str
    action: str
    expire_str: str = None
    lock_state: bool = False

class ResellerCancelInviteRequest(BaseModel):
    ownerid: str
    invite_id: str

class ResellerUserCreateRequest(BaseModel):
    email: str
    appid: str
    username: str
    password: str
    days: int
    expire_str: str = None

class ResellerUserListRequest(BaseModel):
    email: str
    appid: str

class ResellerUserActionRequest(BaseModel):
    email: str
    user_id: str
    action: str
    expire_str: str = None
    lock_state: bool = False

class LogListRequest(BaseModel):
    ownerid: str
    appid: str = None

class LogClearRequest(BaseModel):
    ownerid: str
    appid: str = None

class BlacklistAddRequest(BaseModel):
    ownerid: str
    ip: str
    reason: str = ""

class BlacklistRemoveRequest(BaseModel):
    ownerid: str
    ip: str

class BlacklistListRequest(BaseModel):
    ownerid: str



