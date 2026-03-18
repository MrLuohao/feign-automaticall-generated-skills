# Java Feign Defaults

## 默认 Feign 骨架

- 默认生成 Java interface
- 默认使用 `@FeignClient(name = ..., contextId = ...)`
- 默认不使用 `@FeignClient(path = ...)`
- 方法注解输出完整路径

```java
@FeignClient(name = "service-name", contextId = "UserApi")
public interface UserApi {
}
```

## 默认参数映射

- 参数位置完全以 `Spec` 为准
- `body.type` -> `@RequestBody`
- `pathParams` -> `@PathVariable`
- `queryParams` -> `@RequestParam`
- `headers` -> `@RequestHeader`
- `parts` -> `@RequestPart`
- 不允许生成器猜测参数位置

```java
@PostMapping("/query")
Response<UserVO> query(@RequestBody UserQueryDTO request);
```

## 默认返回规则

- 优先使用 `Spec.response.envelopeType`
- 若 `Spec` 未显式声明，则回退公司默认 `Response<T>`
- `Spec.response.dataType` 作为业务 data 类型

```java
Response<UserVO> query(...);
```

## 默认命名规则

- `Controller -> Api`
- `contextId` 默认与接口名一致
- 方法名默认复用 `Spec.source.methodName`

## 默认路径规则

- 默认路径以 `controller.basePath + method.path` 为主
- 若 `SERVICE.yaml` 显式声明 `pathPrefix`，则在最前面拼接
- 默认不使用 `@FeignClient(path=...)`

## 覆盖边界

### `SERVICE.yaml` 允许覆盖

- `target`
- `contextIdPrefix`
- `pathPrefix`
- `basePathStyle`
- `pathRules.exceptions`

### `SERVICE.yaml` 不允许覆盖

- 参数映射规则
- 方法命名主规则
- DTO 字段生成主规则
- consumer 本地落位规则

### consumer 本地规则边界

consumer 本地规则只允许影响：

- 落位
- 命名

不得影响：

- provider 契约语义
- 参数位置
- 返回包装
- 路径协议
- target 语义
