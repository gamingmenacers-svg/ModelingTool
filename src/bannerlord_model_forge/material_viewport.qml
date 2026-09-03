import QtQuick
import QtQuick3D
import QtQuick3D.AssetUtils
import QtQuick3D.Helpers

Item {
    id: root
    property url modelSource: ""
    property bool baseColorOnly: true
    property string loadError: ""

    Rectangle {
        anchors.fill: parent
        color: "#0d141d"
    }

    View3D {
        anchors.fill: parent
        environment: SceneEnvironment {
            backgroundMode: SceneEnvironment.Color
            clearColor: "#0d141d"
            antialiasingMode: SceneEnvironment.SSAA
            antialiasingQuality: SceneEnvironment.High
            tonemapMode: SceneEnvironment.TonemapModeLinear
            debugSettings.materialOverride: root.baseColorOnly ? DebugSettings.BaseColor : DebugSettings.None
        }

        Node {
            id: cameraOrigin
            // Forge's converted assets retain Blender's Z-up coordinates.
            // This places the initial camera on -Y with +Z as screen-up.
            eulerRotation.x: 90

            PerspectiveCamera {
                id: camera
                position: Qt.vector3d(0, 0, 300)
                eulerRotation.z: 180
                clipNear: 0.1
                clipFar: 10000
            }
        }

        DirectionalLight {
            eulerRotation.x: -35
            eulerRotation.y: -30
            brightness: 2.0
            ambientColor: "#526274"
        }

        DirectionalLight {
            eulerRotation.x: 25
            eulerRotation.y: 150
            brightness: 1.1
        }

        RuntimeLoader {
            id: importedAsset
            source: root.modelSource

            function fitAsset() {
                let low = bounds.minimum
                let high = bounds.maximum
                let dx = high.x - low.x
                let dy = high.y - low.y
                let dz = high.z - low.z
                let diameter = Math.max(dx, dy, dz, 0.0001)
                let factor = 190.0 / diameter
                scale = Qt.vector3d(factor, factor, factor)
                position = Qt.vector3d(
                    -(low.x + high.x) * 0.5 * factor,
                    -(low.y + high.y) * 0.5 * factor,
                    -(low.z + high.z) * 0.5 * factor
                )
            }

            onBoundsChanged: fitAsset()
            onStatusChanged: {
                if (status === RuntimeLoader.Success) {
                    root.loadError = ""
                    Qt.callLater(fitAsset)
                } else if (status === RuntimeLoader.Error) {
                    root.loadError = errorString
                }
            }
        }

        OrbitCameraController {
            origin: cameraOrigin
            camera: camera
        }
    }

    Rectangle {
        anchors.left: parent.left
        anchors.bottom: parent.bottom
        anchors.margins: 16
        width: interactionText.implicitWidth + 22
        height: 30
        radius: 8
        color: "#b8111822"
        border.color: "#33445a"

        Text {
            id: interactionText
            anchors.centerIn: parent
            text: "DRAG TO ORBIT  •  WHEEL TO ZOOM"
            color: "#9fb0c5"
            font.pixelSize: 10
            font.weight: Font.DemiBold
            font.letterSpacing: 1.0
        }
    }

    Rectangle {
        visible: root.loadError.length > 0
        anchors.centerIn: parent
        width: Math.min(parent.width - 48, 560)
        height: errorText.implicitHeight + 32
        radius: 10
        color: "#d1251921"
        border.color: "#8a3e4a"

        Text {
            id: errorText
            anchors.fill: parent
            anchors.margins: 16
            text: "Material preview could not load\n" + root.loadError
            color: "#ffb6be"
            wrapMode: Text.Wrap
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
    }
}
