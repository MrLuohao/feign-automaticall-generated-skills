# Trigger Examples

以下表达都应直接触发本 skill：

- 更新了接口，同步接口文档
- 删除 FoundationAdminController
- 删除这个 controller 对应的 spec/doc
- 为我生成根据用户 id 查询用户信息的 feign 调用代码
- 帮我接一下这个接口
- `com.dst.xxx.controller.UserController`
- `/path/to/UserController.java 为这个 controller 生成接口文档`

以下表达不应单独触发本 skill：

- 帮我优化这个 Java 文件
- 看一下这个 controller
- 生成一段代码
