# <Controller> 接口文档

## Controller 概览

| 项目 | 说明 |
|------|------|
| service | `<service>` |
| domain | `<domain>` |
| basePath | `<base-path>` |
| pathPrefix | `<optional-path-prefix>` |

## 方法摘要

| operationId | 摘要 | 方法 | 路径 |
|------|------|------|------|
| `<operation-id>` | `<summary>` | `<http-method>` | `<full-path>` |

## 1. <summary>

### 基本信息

| 项目 | 说明 |
|------|------|
| operationId | `<operation-id>` |
| method | `<http-method>` |
| path | `<full-path>` |
| description | `<description>` |

### 请求

#### body

| 字段名 | 类型 | 必填 | 说明 |
|------|------|------|------|
| requestBody | `<body-type>` | `<required>` | `<body-description>` |

### 响应

| 项目 | 说明 |
|------|------|
| envelopeType | `<envelope-type>` |
| dataType | `<response-type>` |
| description | `<response-description>` |

### DTO 摘要

#### <DTO>

| 字段名 | 类型 | 必填 | 说明 | 约束 |
|------|------|------|------|------|
| <field-name> | `<field-type>` | `<required>` | `<field-description>` | `<constraints>` |

### 错误信息

| 错误码 | 含义 | 触发条件 |
|------|------|------|
| `<error-code>` | `<meaning>` | `<when>` |

### 源码定位

| 项目 | 说明 |
|------|------|
| className | `<Controller>` |
| methodName | `<method-name>` |
| signature | `<signature>` |
